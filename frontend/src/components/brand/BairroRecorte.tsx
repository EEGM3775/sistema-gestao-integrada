import React from 'react'

/**
 * "O Bairro" (docs/identidade-visual.md §7) — recorte do tecido urbano com o
 * quarteirão-empresa. Uma geometria, duas vidas: de dia masterplan com sombra de
 * sol; de noite janelas acesas e vias com brilho âmbar. Acompanha o tema pelos
 * tokens `--city-*` (index.css). Decorativo: `aria-hidden`, sem interação.
 *
 * É sempre recorte do MESMO tecido (proibição §7: nunca redesenhar por superfície).
 * Aqui o recorte do rodapé da sidebar usa o viewBox `196 30 334 350` do protótipo,
 * com fade no topo. Renderizado como markup fiel via string (é SVG estático).
 */
const FABRIC = `
<svg viewBox="196 30 334 350" preserveAspectRatio="xMidYMax slice"
     style="position:absolute;left:0;right:0;bottom:0;width:100%;height:240px;
     -webkit-mask-image:linear-gradient(180deg,transparent,#000 36%);
     mask-image:linear-gradient(180deg,transparent,#000 36%)">
  <defs>
    <filter id="bairroGlow" x="-60%" y="-60%" width="220%" height="220%">
      <feGaussianBlur stdDeviation="12"/>
    </filter>
  </defs>
  <rect x="352" y="78" width="126" height="103" style="fill:#F2AC46;opacity:var(--city-glow)" filter="url(#bairroGlow)"/>
  <g style="filter:var(--city-shadowf)">
    <path d="M0 0 H80 L92 12 V70 H0 Z" style="fill:var(--city-block)"/>
    <path d="M108 0 H214 V44 H180 V70 H108 Z" style="fill:var(--city-block2)"/>
    <path d="M246 0 H330 V70 H230 Z" style="fill:var(--city-block)"/>
    <path d="M346 0 H426 V70 H358 L346 58 Z" style="fill:var(--city-block2)"/>
    <path d="M442 0 H560 V70 H474 V44 H442 Z" style="fill:var(--city-block)"/>
    <path d="M0 86 H70 V160 L58 173 H0 Z" style="fill:var(--city-block2)"/>
    <path d="M86 86 H184 L200 102 V173 H86 Z" style="fill:var(--city-zorig)"/>
    <path d="M216 86 H344 L330 138 H230 Z" style="fill:var(--city-block)"/>
    <path d="M360 86 H470 V150 H446 V173 H360 Z" style="fill:var(--city-zconst)"/>
    <path d="M500 86 H560 V173 H486 V100 Z" style="fill:var(--city-block2)"/>
    <path d="M0 207 H58 L70 220 V294 H0 Z" style="fill:var(--city-block)"/>
    <path d="M86 207 H200 V278 L186 294 H86 Z" style="fill:var(--city-zoper)"/>
    <path d="M230 242 H330 L344 294 H216 Z" style="fill:var(--city-block2)"/>
    <path d="M360 207 H470 V294 H386 V270 H360 Z" style="fill:var(--city-zneg)"/>
    <path d="M486 207 H560 V294 H500 L486 280 Z" style="fill:var(--city-block)"/>
    <path d="M0 310 H110 L122 322 V380 H0 Z" style="fill:var(--city-block2)"/>
    <path d="M138 310 H252 V368 L240 380 H150 L138 368 Z" style="fill:var(--city-block)"/>
    <path d="M268 310 H380 L366 380 H282 Z" style="fill:var(--city-block2)"/>
    <path d="M410 310 H488 V380 H396 V324 Z" style="fill:var(--city-block)"/>
    <path d="M504 310 H548 L560 322 V380 H504 Z" style="fill:var(--city-block2)"/>
    <line x1="6" y1="190" x2="214" y2="190" style="stroke:var(--city-park)" stroke-width="3" stroke-dasharray="24 12"/>
    <line x1="346" y1="190" x2="554" y2="190" style="stroke:var(--city-park)" stroke-width="3" stroke-dasharray="24 12"/>
    <circle cx="280" cy="190" r="46" style="fill:var(--city-park)"/>
    <circle cx="280" cy="190" r="16" style="fill:var(--ink)"/>
    <g style="fill:#F2AC46;opacity:var(--city-window)">
      <rect x="358" y="16" width="5" height="7" rx="1"/><rect x="372" y="16" width="5" height="7" rx="1"/>
      <rect x="358" y="32" width="5" height="7" rx="1"/>
      <rect x="454" y="12" width="5" height="7" rx="1"/><rect x="468" y="20" width="5" height="7" rx="1"/>
      <rect x="482" y="12" width="5" height="7" rx="1"/>
      <rect x="372" y="100" width="5" height="7" rx="1"/><rect x="386" y="108" width="5" height="7" rx="1"/>
      <rect x="498" y="98" width="5" height="7" rx="1"/><rect x="512" y="106" width="5" height="7" rx="1"/>
      <rect x="498" y="120" width="5" height="7" rx="1"/>
      <rect x="372" y="220" width="5" height="7" rx="1"/><rect x="386" y="228" width="5" height="7" rx="1"/>
      <rect x="372" y="242" width="5" height="7" rx="1"/>
      <rect x="498" y="220" width="5" height="7" rx="1"/><rect x="512" y="228" width="5" height="7" rx="1"/>
      <rect x="498" y="242" width="5" height="7" rx="1"/>
      <rect x="408" y="324" width="5" height="7" rx="1"/><rect x="422" y="332" width="5" height="7" rx="1"/>
      <rect x="516" y="322" width="5" height="7" rx="1"/><rect x="530" y="330" width="5" height="7" rx="1"/>
    </g>
  </g>
  <g stroke="#F2AC46" stroke-width="1.6" fill="none" style="opacity:var(--city-glow)">
    <line x1="334" y1="173" x2="560" y2="173"/>
    <line x1="334" y1="207" x2="560" y2="207"/>
    <circle cx="280" cy="190" r="50"/>
  </g>
</svg>`

export const BairroRecorte: React.FC<{ style?: React.CSSProperties }> = ({ style }) => (
  <div
    aria-hidden="true"
    style={{ position: 'absolute', inset: 0, zIndex: 0, pointerEvents: 'none', ...style }}
    dangerouslySetInnerHTML={{ __html: FABRIC }}
  />
)

export default BairroRecorte
