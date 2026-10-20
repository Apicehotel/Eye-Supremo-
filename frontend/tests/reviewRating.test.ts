import test from 'node:test';
import assert from 'node:assert/strict';
import {normalizedReviewRating,reviewRatingScale,reviewRatingTone} from '../src/lib/reviewRating.ts';

test('normalizza Booking, Google e TripAdvisor sulla stessa scala', () => {
  assert.equal(reviewRatingScale('Booking'), 10);
  assert.equal(reviewRatingScale('Google'), 5);
  assert.equal(reviewRatingScale('TripAdvisor'), 5);
  assert.equal(normalizedReviewRating({source: 'Booking', rating: 8}), 8);
  assert.equal(normalizedReviewRating({source: 'Google', rating: 4}), 8);
  assert.equal(normalizedReviewRating({source: 'TripAdvisor', rating: 4.5}), 9);
});

test('classifica il voto in base alla scala della fonte', () => {
  assert.equal(reviewRatingTone({source: 'TripAdvisor', rating: 4}), 'positive');
  assert.equal(reviewRatingTone({source: 'Google', rating: 3}), 'positive');
  assert.equal(reviewRatingTone({source: 'Booking', rating: 5}), 'negative');
  assert.equal(reviewRatingTone({source: 'Booking', rating: null}), 'unrated');
});
