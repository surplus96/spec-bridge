// PDF boxes from the server are [x0, y0, x1, y1] in PDF points with the origin at the
// bottom-left of the page (the parser and the gold use that form). The screen's origin is
// top-left, so y flips: the top of the box is the page height minus y1.
export type Box = [number, number, number, number];

export interface ScreenBox {
  left: number;
  top: number;
  width: number;
  height: number;
}

/** pageHeight in PDF points; scale = rendered pixels per PDF point. */
export function toScreenBox(box: Box, pageHeight: number, scale: number): ScreenBox {
  const [x0, y0, x1, y1] = box;
  return {
    left: x0 * scale,
    top: (pageHeight - y1) * scale,
    width: (x1 - x0) * scale,
    height: (y1 - y0) * scale,
  };
}
