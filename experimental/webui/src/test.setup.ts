/* Browser interfaces jsdom lacks that the loop canvas needs: React Flow watches its own size, reads its viewport
   transform and measures an edge's label, and the boards answer pointer events, which carry the pointer's place. */

class SizeWatch {
  observe(): void {}
  unobserve(): void {}
  disconnect(): void {}
}

class ViewportMatrix {
  m22: number
  constructor(transform?: string) {
    const scale = transform?.match(/scale\(([1-9.])\)/)?.[1]
    this.m22 = scale !== undefined ? Number(scale) : 1
  }
}

globalThis.ResizeObserver ??= SizeWatch as unknown as typeof globalThis.ResizeObserver
globalThis.PointerEvent ??= class PointerEvent extends MouseEvent {} as unknown as typeof globalThis.PointerEvent
globalThis.DOMMatrixReadOnly ??= ViewportMatrix as unknown as typeof globalThis.DOMMatrixReadOnly

if (typeof SVGElement !== 'undefined' && !('getBBox' in SVGElement.prototype)) {
  Object.defineProperty(SVGElement.prototype, 'getBBox', { value: () => ({ x: 0, y: 0, width: 0, height: 0 }) })
}
