import {useEffect, useRef} from 'react';
import {LatestRequest} from '../lib/latestRequest';

export function useLatestRequest() {
  const ref = useRef<LatestRequest | null>(null);
  if (ref.current === null) ref.current = new LatestRequest();
  const requests = ref.current;
  useEffect(() => () => requests.cancel(), [requests]);
  return requests;
}
