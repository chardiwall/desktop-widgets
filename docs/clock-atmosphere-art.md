# Clock atmosphere artwork

The built-in ImageGen tool generated one transparent vignette per Clock variant. The production images are in `desktop_widgets/widgets/clock/art/` with the suffix `-atmosphere.png`. They use the clock’s existing mirroring and opacity controls. The export trims transparent padding above the art, downsamples the RGBA output, and tapers the alpha on the inward edge so clouds blend into the card.

## Shared prompt

```text
Use case: stylized-concept. Asset type: genuinely transparent PNG background vignette for a bilingual desktop clock widget. Wide landscape source, about 3:2 canvas. Create one illustration. All painted content is in the LOWER 55% of the canvas and extends to the bottom and right canvas boundaries, with the upper 45% transparent. The dominant subject sits in the right third and is large, about half the height of the artwork area, some foreground may crop off at the bottom and right. A broad trail of soft atmosphere and ground stretches almost to the left edge, naturally fading to full transparency toward left and top. The left 35% stays faint and low-contrast for foreground UI. PNG with genuinely transparent alpha. No filled sky rectangle, matte, background block, checkerboard, solid upper background, text, numerals, clock face, border, watermark, or UI. Painted, atmospheric, refined, restrained palette with clear near/middle/far depth. Motifs must be discernible at small scale.
```

## Scene prompts

Each generation appends its scene below to the shared prompt.

### lantern-a

```text
A hammered-brass mabkhara incense burner resting on a low stone ledge at the far right, warm embers and one delicate ribbon of oud smoke curling inward through violet air. An understated engraved star on the burner. Large readable silhouette, clearly an incense burner rather than a hanging lamp. Aubergine, antique brass, subdued lavender.
```

### lantern-b

```text
An old brass oil lamp with a tiny amber flame on a tiled rooftop parapet at far right, one wispy thread of smoke, deep indigo-violet evening air, broad low rose-gray cloud ribbons and a far-away apricot afterglow. The top of the parapet is seen in perspective. No distant skyline or crescent. Quiet Persian miniature-inspired tonal brushwork.
```

### blueprint-a

```text
An Islamic observatory rooftop at early dawn, a single clearly recognizable mosque with a tall minaret and ribbed dome at the right, seen behind the rooftop from a distance. Low layers of blue-gray cloud curl past their base and extend across nearly the whole bottom. Deep Prussian blue and teal haze, satin brass light on the right edge. Give the silhouette enough vertical scale to be recognizable at widget size; no decorative arches or ornamental border.
```

### blueprint-b

```text
A large brass and lapis Islamic armillary sphere with three clearly legible concentric bands, mounted on a dark masonry platform at far right, some of the outer ring cropped by right wall. Broad, soft bands of midnight-blue and cyan cloud drift behind the instrument along the bottom, with a few distant pinpoint stars. Incised metal, matte midnight blues, tarnished brass. No mosque, no building, no drawn chart or writing.
```

### oasis-a

```text
Water overflowing from a large carved stone fountain basin into a runnel at right, a few bronze-green maidenhair ferns along the bottom lip and a pale horizontal veil of cool dawn vapor just above the water flowing left. Jade, celadon, dark emerald and restrained old brass glints. Readable overlapping tiers, no water lily, window, architecture or skyline.
```

### oasis-b

```text
A dark olive tree at far right, twisting trunk and masses of dusty sage leaves rising from stone irrigation terraces with broad low jade and sage morning mist spreading left across the base. A sliver of pale warm dawn through the mist. Gouache with a subdued green palette. No building, no window and no ornamental flowers.
```

### warm-earth-a

```text
Weather-worn sandstone wind tower with deep narrow vents on a terraced roof at far right, subtle apricot sand haze swept low to the left and several wide thin high clouds of pale buff pink. Small clay jars near the tower base for scale. Sun-baked ivory, ochre and burnished sienna. No caravan, no dunes, no palms. Tonal watercolor and dry brush on warm plaster.
```

### warm-earth-b

```text
A pair of large unglazed terracotta water jars on low ochre steps at far right, a draped woven cloth with a subtle rust-and-cream stripe, and wide wind-swept amber dust ribbons wrapping the base and tapering left. One restrained faint rose cloud in the distance. Warm paper cream, cinnamon clay, muted burnt sienna. Watercolor and dry brush with light restful highlights.
```

### graphite-a

```text
An ink-dark slate ridge with a broad low band of luminous lavender-gray fog rolling through split layers of stone. One jagged stratum at the right gives this a bold recognizable shape and depth. A few sparse pale lichen flecks on the stone. Moonless, desaturated graphite, lilac and smoke. No vines, blooms, stars or ornate border.
```

### graphite-b

```text
A rough, charcoal-black coastal sea stack at the far right rising out of a steel-gray night sea, peaks obscured by broad silver-lilac maritime fog and clouds, with a quiet line of ripples fading along the bottom to the left. Large silhouette and moody graphite and chalk gouache, subtle violet. No flowers, writing, forest or mountain range.
```
