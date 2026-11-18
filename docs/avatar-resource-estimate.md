# Ubuntu avatar resource and battery estimate

For the pilot, aim for **under 0.10 W of average additional battery draw** and a **24 MiB limit on retained pixel buffers and textures**. Keep the avatar still between activities and stop its animation work when covered. A scenario with five seconds of motion after two minutes of rest comes out to **about 0.03–0.09 W**, using the power assumptions below. Measure the real difference once AzClock can play one complete walk.

## What this machine reported

| Reading | Observed value |
| --- | --- |
| Test host | Ubuntu 26.04.1 LTS, GNOME Shell 50.1, Wayland, Intel Core Ultra 9 185H |
| Battery at full charge | 61.258 Wh reported, 71.008 Wh design capacity |
| Whole-laptop draw with the avatar absent | 13 readings over 60 seconds while discharging. Mean 14.27 W, median 13.90 W, range 12.95–18.32 W. |
| Battery energy counter | Reported 61.258 Wh at both endpoints. Use the mean of the power readings as a scenario reference. The short sample cannot resolve a change in battery drain. |
| Graphics | Intel integrated GPU active. NVIDIA RTX 4070 Laptop GPU runtime-suspended at the status check. |

The battery readings include the screen, compositor and the current workload. Keep the display mode and workload fixed when measuring the avatar. The session could read the battery gauge but lacked access to the Intel RAPL energy counter. [Linux power supply readings](https://docs.kernel.org/power/power_supply_class.html) · [Linux PCI runtime power management](https://docs.kernel.org/power/pci.html)

## Disk, RAM and texture estimates

The 264 source PNGs total 28.14 MiB on disk and 181.27 MiB as decoded 8-bit RGBA. The union of their nontransparent bounds is 193 × 342 pixels inside the 360 × 500 source canvas. The table uses that same crop for every frame, scaled to the settings preview's 145-pixel-wide source image at the selected avatar and display scale. Preserve the crop origin as an offset from the source pivot. Measure new activities independently because a horizontal push-up or extended grip can have larger bounds. [Blender export settings](../character/3d/anim.py) · [Settings preview](../work/desktop-widget-settings.html)

| Asset size | RGBA per frame | Four seconds at 30 fps, one copy | Four seconds if pixel buffer and texture both retained |
| --- | ---: | ---: | ---: |
| Original 360 × 500 | 0.687 MiB | 82.4 MiB | 164.8 MiB |
| Default size at 1×, 78 × 138 | 0.041 MiB | 4.9 MiB | 9.9 MiB |
| Default size at 2×, 156 × 276 | 0.164 MiB | 19.7 MiB | 39.4 MiB |
| Largest preview size at 2×, 203 × 359 | 0.278 MiB | 33.4 MiB | 66.7 MiB |

These are pixel counts. Driver layout, texture padding, actor objects and temporary buffers add overhead. A four-second clip fits the budget at 1×. At 2×, it fits only if the retained representation and staging buffers stay below the cap. Charge the still frame, props, textures and decode buffers against the same budget. Release staging pixels after upload when the API permits. For a larger clip, try a smaller display-size tier or a bounded buffer of upcoming frames. Use the still pose if preparation cannot keep playback within budget. [GNOME Shell texture upload](https://gnome.pages.gitlab.gnome.org/gnome-shell/st/method.ImageContent.set_bytes.html)

An in-memory Pillow check on this machine decoded the 264 source frames in **565 ms of CPU time** and a temporary 1× version in **58 ms**. These are medians across five runs using pre-read PNG bytes. The temporary PNGs totalled **3.33 MiB** and were kept in memory for the check. A 120-frame clip at comparable complexity would take roughly 257 ms or 26 ms of decode CPU time respectively. These numbers exclude disk latency, texture upload and the Shell compositor. Do the preparation ahead of playback and check the actual GJS loading and upload path with a profiler. Even 26 ms in one Shell callback can cross a refresh deadline.

## CPU, GPU and wakeups

- **Hidden or locked.** Budget zero avatar animation callbacks, redraws or texture uploads. A configured prayer reminder or active focus session can still use a deadline. The normal timer setup should avoid any avatar wakeup between deadlines while hidden.
- **Visible and still.** Keep one prepared pose. At the proposed 60–180 second rest interval, the ambient scheduler averages roughly 30 selection wakeups per visible hour before allowing for time spent in activities. A held pose, readable ayah or prayer bubble needs only its own next change deadline. A static actor may still be composited when AzClock or another actor redraws.
- **Moving.** At 60–120 compositor ticks per second, an assumed 0.1–0.5 ms of avatar-side work per tick uses roughly **0.6–6% of one CPU core while active**, or **0.02–0.24% averaged across a 4% motion duty cycle**. This is a CPU budget model. It excludes clip preparation and Mutter's rendering and driver work. At default 1× or 2×, uploading a new raw texture on every 30 fps sprite change would move roughly 1.2 or 4.9 MiB/s of pixel data. Reuse prepared textures when they fit and keep animation redraws local to the avatar and active prop. Measure compositor work separately from script CPU.
- **Hybrid GPU.** Use the existing GNOME compositor path. Check that the avatar does not wake the NVIDIA GPU under the same display setup when it would otherwise be suspended. Compare runtime status using sysfs. Running a GPU diagnostic that opens the device can interfere with this check. [GJS event loop](https://gjs.guide/guides/gjs/asynchronous-programming.html) · [Clutter animation timing](https://gnome.pages.gitlab.gnome.org/mutter/clutter/class.Timeline.html) · [Linux runtime power management](https://docs.kernel.org/driver-api/pm/devices.html)

## Battery scenarios

Assume the still avatar adds 0.01 W and active 2D animation adds another 0.5–2 W while playing. These are inputs for sensitivity analysis, with no measurement of this avatar or its compositor overhead yet. At five seconds of moving time after two minutes of rest, the motion duty cycle is 4%. The resulting average is 0.03–0.09 W. A busy pattern of ten seconds of motion after one minute of rest raises it to 14%, or about 0.08–0.30 W. Count only frames that actually animate, and include clip preparation in the eventual measured average.

| Added average draw | Illustrative time lost from a full charge at the observed 14.27 W reference |
| ---: | ---: |
| 0.05 W | 0.9 min |
| 0.10 W | 1.8 min |
| 0.25 W | 4.4 min |
| 0.50 W | 8.7 min |
| 1.00 W | 16.9 min |

The calculation uses full-charge capacity divided by total draw, and the reference works out to about 4 h 18 min. These are illustrative steady-workload runtimes. The same added load has a greater effect on a laptop that is otherwise drawing less power. Gemini and Blender authoring are outside this runtime estimate.

## First measurement gate

User-requested listening and rain sustain visual effects while visible. The short-walk duty-cycle estimate applies to ambient mode. Add separate audio-only, visible listening and rain runs to isolate decoder and compositor overhead.

1. Compare the same AzClock configuration with avatar off, visible but still, visible with seeded activities, and hidden. Keep the display mode and brightness, power profile, workspace, other apps and graphics setup fixed across runs. Run on battery away from the 100% plateau and check that the energy gauge advances before comparing results.
2. Alternate off and on runs, warm up the display and session first, and repeat. Start with runs of at least 30 minutes, extending them if the battery gauge or background variation is too coarse. A 0.10 W difference changes battery energy by only 0.05 Wh over 30 minutes. Use energy change over the run and report the paired difference and variation. If the difference is below repeatable resolution, report that limit. A separate continuous-motion run can help isolate the active cost. Report it separately from typical use.
3. Profile GNOME Shell with Sysprof in separate runs. Record frame deadlines, avatar callback time, steady and peak pixel residency, and idle or hidden wakeups. Verify no residency growth across repeated activities, no avatar work left after disable, and no avatar-triggered resume of the NVIDIA GPU.
4. Tune activity frequency and texture sizes from those results. Investigate a repeatable overhead above 0.25 W in normal use before enabling ambient activity by default. Keep the same visible frame pacing on battery and spend less time animating if needed. [GNOME power measurement tools](https://docs.gtk.org/gio/iface.PowerProfileMonitor.html) · [Sysprof](https://apps.gnome.org/Sysprof/)
