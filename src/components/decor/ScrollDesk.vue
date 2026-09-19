<template>
  <!-- Storyteller's desk: scrolls, quill & ink, books, a tiny sprite. -->
  <svg class="desk" viewBox="0 0 224 158" aria-hidden="true" focusable="false">
    <!-- table shadow -->
    <ellipse cx="112" cy="140" rx="100" ry="12" fill="#d9c39a" opacity=".38" />

    <!-- large scroll, gently unrolled -->
    <g transform="rotate(-7 108 86)">
      <rect x="34" y="62" width="150" height="42" rx="4" fill="#ead7ae" />
      <rect x="34" y="62" width="150" height="42" rx="4" fill="url(#scrollSheen)" opacity=".5" />
      <!-- rolled ends -->
      <circle cx="34" cy="83" r="21" fill="#dcc191" />
      <circle cx="34" cy="83" r="21" fill="none" stroke="#b99a66" stroke-width="1.4" />
      <path
        d="M34 83m-11 0a11 11 0 1 1 22 0a11 11 0 1 1 -22 0"
        fill="none"
        stroke="#b99a66"
        stroke-width="1.2"
        opacity=".8" />
      <circle cx="184" cy="83" r="21" fill="#dcc191" />
      <circle cx="184" cy="83" r="21" fill="none" stroke="#b99a66" stroke-width="1.4" />
      <path
        d="M184 83m-11 0a11 11 0 1 1 22 0a11 11 0 1 1 -22 0"
        fill="none"
        stroke="#b99a66"
        stroke-width="1.2"
        opacity=".8" />
      <!-- cross ties -->
      <path d="M78 60v46M140 60v46" stroke="#93764d" stroke-width="2.4" opacity=".65" />
      <!-- faint writing lines -->
      <path
        d="M52 73h34M52 81h30M52 89h36M124 73h40M124 81h34M124 89h42"
        stroke="#a98d5f"
        stroke-width="1.1"
        opacity=".45" />
    </g>

    <!-- small scroll tube at the front -->
    <g transform="rotate(4 60 122)">
      <rect
        x="12"
        y="112"
        width="86"
        height="19"
        rx="9.5"
        fill="#dfc59b"
        stroke="#b99a66"
        stroke-width="1.2" />
      <ellipse cx="98" cy="121.5" rx="5" ry="9.5" fill="#c9ac7c" />
    </g>

    <!-- inkwell -->
    <g>
      <rect x="122" y="96" width="30" height="26" rx="7" fill="#25333d" />
      <rect x="128" y="88" width="18" height="12" rx="3.5" fill="#2d3e49" />
      <ellipse cx="137" cy="90" rx="9" ry="3.2" fill="#141d24" />
      <rect x="126" y="104" width="22" height="6" rx="2" fill="#b3945d" opacity=".85" />
      <path
        d="M137 106l1.1 2.9 3 .3-2.2 2 .6 3-2.5-1.5-2.5 1.5.6-3-2.2-2 3-.3Z"
        fill="#e7d9a8"
        opacity=".9" />
    </g>

    <!-- quill -->
    <g>
      <path
        d="M151 74C139 46 131 33 140 17c13 11 20 26 22 42 .6 7-2.6 12.6-11 15Z"
        fill="#33454f" />
      <path d="M151 74c-7-16-11.5-30.5-9.5-45" fill="none" stroke="#1f2c34" stroke-width="1.6" />
      <path
        d="M145 58l-8-4M148 66l-9-3M142 47l-7-5M140 36l-6.5-4.5"
        stroke="#42585f"
        stroke-width="1.4"
        opacity=".8" />
      <path d="M151 74l-8 12.5" stroke="#1f2c34" stroke-width="2.6" stroke-linecap="round" />
    </g>

    <!-- stacked books -->
    <g>
      <g transform="rotate(-4 176 126)">
        <rect x="150" y="118" width="56" height="15" rx="3" fill="#8a5a3f" />
        <rect x="150" y="126" width="56" height="5" rx="2" fill="#f1e4c4" />
        <rect
          x="150"
          y="118"
          width="56"
          height="15"
          rx="3"
          fill="none"
          stroke="#6d432d"
          stroke-width="1.1" />
      </g>
      <g transform="rotate(3 178 112)">
        <rect x="156" y="104" width="50" height="14" rx="3" fill="#2f5f59" />
        <rect x="156" y="111" width="50" height="5" rx="2" fill="#f1e4c4" />
        <path d="M161 104v14M199 104v14" stroke="#b3945d" stroke-width="2" opacity=".85" />
        <rect
          x="156"
          y="104"
          width="50"
          height="14"
          rx="3"
          fill="none"
          stroke="#234a46"
          stroke-width="1.1" />
      </g>
    </g>

    <!-- little wildflower -->
    <g transform="translate(64 52)">
      <path
        d="M6 16C6 9 3 5 0 3"
        fill="none"
        stroke="#7c8f56"
        stroke-width="1.6"
        stroke-linecap="round" />
      <g fill="#fbf4e4" stroke="#c9ac7c" stroke-width=".8">
        <ellipse cx="10" cy="4.5" rx="2.5" ry="4" />
        <ellipse cx="10" cy="4.5" rx="2.5" ry="4" transform="rotate(72 10 4.5)" />
        <ellipse cx="10" cy="4.5" rx="2.5" ry="4" transform="rotate(144 10 4.5)" />
        <ellipse cx="10" cy="4.5" rx="2.5" ry="4" transform="rotate(216 10 4.5)" />
        <ellipse cx="10" cy="4.5" rx="2.5" ry="4" transform="rotate(288 10 4.5)" />
      </g>
      <circle cx="10" cy="4.5" r="2.1" fill="#d9a83e" />
    </g>

    <!-- tiny sprite by the scroll -->
    <g>
      <path d="M22 96c4.5-6 9.5-6 13.5 0-4.5 5.5-9.5 5.5-13.5 0Z" fill="#dfe9c4" opacity=".9" />
      <path d="M27 102l4.5 8-9-2Z" fill="#2f5f59" />
      <circle cx="27" cy="99" r="4" fill="#e2b685" />
      <path d="M24.5 97.5q2.5-3.5 5-1" fill="#6b4a2f" />
    </g>

    <defs>
      <linearGradient id="scrollSheen" x1="0" y1="0" x2="0" y2="1">
        <stop offset="0" stop-color="#fff8e6" />
        <stop offset=".5" stop-color="#fff8e6" stop-opacity="0" />
        <stop offset="1" stop-color="#b9955f" stop-opacity=".35" />
      </linearGradient>
    </defs>
  </svg>
</template>

<style scoped>
.desk {
  filter: drop-shadow(0 10px 10px rgba(120, 92, 48, 0.18));
}
</style>
