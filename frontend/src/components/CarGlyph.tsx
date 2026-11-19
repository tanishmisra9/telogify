import { useId, type CSSProperties } from 'react'

export const CAR_W = 26
export const CAR_H = 12

// One flat, top-down car drawn from geometry (no F1 art). The NOSE is the data point: a car's nose sits exactly on
// its value and points toward the faster / gained end, so the tip of the glyph IS the number. The symbol is defined
// once per chart svg under a per-instance id: a shared global id would resolve to the first chart in the document,
// which can sit inside a collapsed (display:none) section. Fill and stroke come from CSS variables set on each <use>
// (custom properties inherit into the shadow tree), so one symbol serves every team colour and the hollow variant.
export function useCarId() {
  return `car-${useId().replace(/:/g, '')}`
}

export function CarDefs({ id }: { id: string }) {
  return (
    <defs>
      <symbol id={id} viewBox={`0 0 ${CAR_W} ${CAR_H}`} width={CAR_W} height={CAR_H} overflow="visible">
        <g strokeLinejoin="round" strokeWidth={0.9} stroke="var(--car-stroke)">
          {/* wheels first so the body overlaps their inner edge */}
          <rect x={5} y={0.6} width={4.2} height={2.8} fill="var(--car-wheel)" />
          <rect x={5} y={8.6} width={4.2} height={2.8} fill="var(--car-wheel)" />
          <rect x={16} y={0.3} width={5.2} height={3.2} fill="var(--car-wheel)" />
          <rect x={16} y={8.5} width={5.2} height={3.2} fill="var(--car-wheel)" />
          {/* front wing, rear wing, body */}
          <rect x={0.6} y={2.4} width={2.4} height={7.2} fill="var(--car-fill)" />
          <rect x={23.2} y={1.6} width={2.4} height={8.8} fill="var(--car-fill)" />
          <path d="M3 5.1 L9 4.5 L13.5 3.5 L21 4 L23.2 5 L23.2 7 L21 8 L13.5 8.5 L9 7.5 L3 6.9 Z" fill="var(--car-fill)" />
        </g>
      </symbol>
    </defs>
  )
}

/** (x, y) is the nose and the car's vertical centre. Faces left by default (body extends right); `faceRight` mirrors it
 * so the body extends left of the nose. `hollow` = a car with no value (no time, out): no fill, muted outline. */
export function Car({
  id, x, y, color, hollow = false, faceRight = false,
}: { id: string; x: number; y: number; color: string; hollow?: boolean; faceRight?: boolean }) {
  const style = {
    '--car-fill': hollow ? 'transparent' : color,
    '--car-wheel': hollow ? 'transparent' : 'var(--color-ink)',
    '--car-stroke': hollow ? 'var(--color-muted)' : 'var(--color-ink)',
  } as CSSProperties
  const transform = faceRight ? `translate(${x} ${y - CAR_H / 2}) scale(-1 1)` : `translate(${x} ${y - CAR_H / 2})`
  return (
    <g transform={transform} style={style} aria-hidden>
      <use href={`#${id}`} />
    </g>
  )
}
