<template>
  <!-- a small stack of worn books with ivy, for the inspiration rail -->
  <svg class="ivy" viewBox="0 0 150 96" aria-hidden="true" focusable="false">
    <!-- ivy behind -->
    <g fill="#7c9360" opacity=".85">
      <path
        d="M96 12c14-9 30-8 44 2-13 9-30 9-44-2Z"
        transform="translate(-8 4) rotate(14 100 16)" />
      <path d="M110 30c12-8 26-7 38 2-11 8-26 8-38-2Z" transform="rotate(-24 128 32)" />
    </g>
    <path
      d="M146 8c-14 6-26 4-36 12s-16 10-24 22"
      fill="none"
      stroke="#5f7549"
      stroke-width="1.6"
      stroke-linecap="round"
      opacity=".7" />
    <g fill="#6f875a" opacity=".9">
      <path d="M122 10c4-4 10-4 13 0-4 4-10 5-13 0Z" />
      <path d="M108 18c4-4 10-4 13 0-4 4-10 4-13 0Z" transform="rotate(20 114 18)" />
      <path d="M92 32c4-4 10-4 13 0-4 4-10 4-13 0Z" transform="rotate(-30 98 32)" />
    </g>

    <!-- bottom book: brown -->
    <g>
      <rect x="28" y="66" width="98" height="19" rx="4" fill="#8a5a3f" />
      <rect x="28" y="78" width="98" height="5" rx="2" fill="#f1e4c4" />
      <path d="M40 66v19M114 66v19" stroke="#b3945d" stroke-width="2.4" opacity=".85" />
      <rect
        x="28"
        y="66"
        width="98"
        height="19"
        rx="4"
        fill="none"
        stroke="#6d432d"
        stroke-width="1.2" />
    </g>
    <!-- middle book: navy, overhangs -->
    <g transform="rotate(-3 66 56)">
      <rect x="20" y="47" width="96" height="18" rx="4" fill="#2f4d6e" />
      <rect x="20" y="58" width="96" height="5" rx="2" fill="#f1e4c4" />
      <path d="M34 47v18M102 47v18" stroke="#c9a959" stroke-width="2.2" opacity=".9" />
      <rect
        x="20"
        y="47"
        width="96"
        height="18"
        rx="4"
        fill="none"
        stroke="#243c58"
        stroke-width="1.2" />
    </g>
    <!-- top book: teal, tilted, bookmark -->
    <g transform="rotate(6 74 36)">
      <rect x="36" y="27" width="82" height="17" rx="4" fill="#2f5f59" />
      <rect x="36" y="37" width="82" height="5" rx="2" fill="#f1e4c4" />
      <path d="M50 27v17M92 27v17" stroke="#b3945d" stroke-width="2.2" opacity=".9" />
      <rect
        x="36"
        y="27"
        width="82"
        height="17"
        rx="4"
        fill="none"
        stroke="#234a46"
        stroke-width="1.2" />
      <path d="M72 44l4 9 4-9" fill="#9a3b3b" />
    </g>
    <!-- tiny flower -->
    <g transform="translate(122 44)">
      <g fill="#fbf4e4" stroke="#c9ac7c" stroke-width=".7">
        <ellipse rx="2" ry="3.4" cy="-3.4" />
        <ellipse rx="2" ry="3.4" cy="-3.4" transform="rotate(72)" />
        <ellipse rx="2" ry="3.4" cy="-3.4" transform="rotate(144)" />
        <ellipse rx="2" ry="3.4" cy="-3.4" transform="rotate(216)" />
        <ellipse rx="2" ry="3.4" cy="-3.4" transform="rotate(288)" />
      </g>
      <circle r="1.8" fill="#d9a83e" />
    </g>
  </svg>
</template>

<style scoped>
.ivy {
  filter: drop-shadow(0 6px 6px rgba(120, 92, 48, 0.16));
}
</style>
