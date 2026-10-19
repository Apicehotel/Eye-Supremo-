/** Cancella il lavoro precedente e impedisce alle risposte tardive di aggiornare la UI. */
export class LatestRequest {
  private controller: AbortController | undefined;

  start() {
    this.cancel();
    const controller = new AbortController();
    this.controller = controller;
    return {signal: controller.signal, current: () => this.controller === controller && !controller.signal.aborted};
  }

  cancel() {
    this.controller?.abort();
    this.controller = undefined;
  }
}
