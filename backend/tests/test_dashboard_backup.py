import json
import sqlite3
import zipfile
from datetime import date
from decimal import Decimal

from app.config import settings
from app.dashboard_service import dashboard_snapshot
from app.models import CentralInvoiceCache, Invoice, Product, Supplier
from app.services import create_backup


def cached(db, key, number, total, issued=date(2026,1,1), supplier='Fornitore', payload='{}'):
    db.add(CentralInvoiceCache(source_hash=key,invoice_number=number,invoice_date=issued,
           supplier_name=supplier,total=Decimal(total),search_text='',payload_json=payload))
    db.commit()


def test_dashboard_only_credit_notes_is_valid(db):
    cached(db,'credit','NC-1','-15')
    result=dashboard_snapshot(db)
    assert result['kpis']['invoices']==0 and result['kpis']['total_spent']==0
    assert result['period']['from'] is None and result['recent']==[]
    assert result['period']['credit_documents']==1 and result['period']['credit_total']==-15


def test_dashboard_merges_sources_and_deduplicates_hash_and_document(db):
    supplier=Supplier(ragione_sociale='Fornitore')
    db.add(supplier);db.flush()
    db.add_all([Invoice(supplier_id=supplier.id,numero='A',data=date(2026,1,1),totale=100,hash_file='same'),
                Invoice(supplier_id=supplier.id,numero='B',data=date(2026,1,2),totale=200),
                Invoice(supplier_id=supplier.id,numero='ONLY-LOCAL',data=date(2026,2,1),totale=300)])
    db.add(Product(nome_canonico='Prodotto locale'));db.commit()
    cached(db,'same','A','100')
    cached(db,'other-hash','B','200',date(2026,1,2),' fornitore ')
    cached(db,'remote','ONLY-CACHE','400',date(2026,3,1))
    result=dashboard_snapshot(db)
    assert result['kpis']['invoices']==4 and result['kpis']['total_spent']==1000
    assert result['kpis']['products']==1 and result['kpis']['suppliers']==1
    assert [r['numero'] for r in result['recent']]==['ONLY-CACHE','ONLY-LOCAL','B','A']
    assert sum(v['total'] for v in result['monthly'])==1000


def test_dashboard_invalid_cached_payload_and_latest_24_months(db):
    for i in range(26):
        cached(db,str(i),str(i),'10',date(2020+i//12,1+i%12,1),payload='broken JSON')
    result=dashboard_snapshot(db)
    assert len(result['monthly'])==24
    assert result['monthly'][0]['month']=='2020-03'
    assert result['recent'][0]['imponibile']==0


def test_backup_restores_committed_wal_and_excludes_uncommitted_data(tmp_path, monkeypatch):
    monkeypatch.setattr(settings,'data_dir',tmp_path)
    db=sqlite3.connect(tmp_path/'eye-supremo.db')
    try:
        db.execute('PRAGMA journal_mode=WAL');db.execute('PRAGMA wal_autocheckpoint=0')
        db.execute('create table purchases(id integer primary key, note text)')
        db.execute("insert into purchases values(1,'committed')");db.commit()
        db.execute("insert into purchases values(2,'uncommitted')")
        (tmp_path/'uploads').mkdir();(tmp_path/'uploads'/'invoice.xml').write_text('<invoice/>')
        archive=create_backup()
        with zipfile.ZipFile(archive) as backup:
            assert backup.testzip() is None
            assert 'eye-supremo.db-wal' not in backup.namelist()
            assert 'eye-supremo.db-shm' not in backup.namelist()
            assert 'uploads/invoice.xml' in backup.namelist()
            backup.extract('eye-supremo.db',tmp_path/'restore')
            assert json.loads(backup.read('backup-manifest.json'))['integrity_check']=='ok'
        with sqlite3.connect(tmp_path/'restore'/'eye-supremo.db') as restored:
            assert restored.execute('PRAGMA integrity_check').fetchone()==('ok',)
            assert restored.execute('select * from purchases').fetchall()==[(1,'committed')]
    finally:db.close()


def test_backup_names_do_not_collide_and_do_not_include_prior_backups(tmp_path,monkeypatch):
    monkeypatch.setattr(settings,'data_dir',tmp_path)
    with sqlite3.connect(tmp_path/'eye-supremo.db') as db:db.execute('create table sample(id integer)')
    first=create_backup();second=create_backup()
    assert first!=second and first.is_file() and second.is_file()
    with zipfile.ZipFile(second) as archive:
        assert all(not name.startswith('backups/') for name in archive.namelist())


def test_corrupt_database_does_not_publish_backup(tmp_path,monkeypatch):
    monkeypatch.setattr(settings,'data_dir',tmp_path)
    (tmp_path/'eye-supremo.db').write_bytes(b'not a database')
    import pytest
    with pytest.raises(sqlite3.DatabaseError):create_backup()
    assert list((tmp_path/'backups').iterdir())==[]


def test_dashboard_endpoints_are_consistent_and_keep_cached_catalog_count(client, db):
    from app.models import AppSetting
    cached(db,'credit','NC-1','-15')
    db.add(AppSetting(key='dashboard_product_count',value='123'));db.commit()
    main=client.get('/api/dashboard').json()
    central=client.get('/api/eye/central/summary').json()
    assert main['kpis']==central['kpis']
    assert main['kpis']['products']==123
    assert main['period']['credit_total']==-15
