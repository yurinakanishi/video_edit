# 260526 Birthday Video Editing Instructions

## Source Handling

- Use the current files that exist under `projects/260526-birthday/source`.
- For still images, use only files under `projects/260526-birthday/source/phtp2605269`.
- Do not use still images from any other source subfolder, including the `todoroki260526...` folder.
- Keep the extracted still `photo_056_DJI_20000104170445_0011_D_t004_5.png` in source if present, but do not use it in the timeline.
- Add the moved stills `photo_057_ST-686.jpg` and `photo_058_ST-723.jpg`, moved from `C:\Users\yurin\Downloads\FOLDER01`, as valid project still images under `source/phtp2605269`.
- Add `photo_059_ST-677.jpg`, copied from `C:\Users\yurin\Downloads\FOLDER01\ST-677.jpg`, as a valid project still image under `source/phtp2605269`.
- Source media has been renamed into readable sequential names while keeping the original stem at the end:
  - videos: `video_###_<original-name>.<ext>`
  - still images: `photo_###_<original-name>.<ext>`
  - audio: `audio_###_<original-name>.<ext>`
  - DJI sidecars: `sidecar_###_<original-name>.<ext>`
- The rename manifest is `projects/260526-birthday/output/reports/source_rename_manifest.json`.
- The build script must compare source rules by the original identity stem after removing the sequential prefix, so old instructions such as `ST-621` and `DJI_20000104172535_0017_D` continue to work after renaming.
- Some source videos may have been deleted by the user after earlier renders. Re-scan `source` before each new timeline build and do not use missing files from old reports.
- Exclude any deleted source videos. In particular, do not use `DJI_20000104185004_0032_D.MP4`; it has been removed from source.
- Do not use these videos or their source files in future previews:
  - `DJI_20000104170051_0008_D`
  - `DJI_20000104174652_0024_D`
  - `DJI_20000104174953_0026_D`
  - `DJI_20000104174803_0025_D`
  - `DJI_20000104172535_0017_D`
  - `DJI_20000104175228_0028_D`
  - `DJI_20000104175108_0027_D`
  - `ST7_8342`
  - `a2ecf072-e001-453b-8432-780011ee6fea`
  - `e6eeaf64-3602-4238-af85-8ccfc6701205`
  - `4e1e990e-0b3c-404c-9fb0-ef25073073ea`
  - `8ea3f1b6-af35-4c9b-9576-71eba58d9f5e`
  - `503179b6-95c2-4918-8c7c-4efc3014d757`
- Exception: use the newly moved source clip `source/video/video_023_a2ecf072-e001-453b-8432-780011ee6fea_clip56_89-114_43.mp4`. This is a trimmed review clip supplied later by the user, not the excluded original `video_020_a2ecf072-e001-453b-8432-780011ee6fea.mp4`.
- Do not use `source/video/video_018_0875db90-5d21-463d-b4b0-9f0a19195ca2.mp4`; remove it completely from the timeline.
- Exception: use `source/mp4/video_014_ST7_8341.MP4` only as two fixed middle timeline clips: `0:00-0:46` and `3:37-3:53`. Do not use any other part of `ST7_8341`.
- After excluding those videos, stretch the remaining videos to maintain the target duration. Use the video-analysis selected sample time and top visual/person-scored moments as the center of the longer clip, instead of extending arbitrary parts.
- It is acceptable to omit some videos if the timeline would exceed 15 minutes, but use the available videos and images as evenly as possible.
- Use the current still images, but do not repeat near-identical photos. Detect visually duplicated stills with perceptual hashing and keep the best-looking one from each duplicate group.
- Do not use still image `ST-610`.
- Do not use `ST-641` / `ST-641w`.
- Do not use `ST-621` or `ST-624`; these correspond to the still images that appeared around `0:41` and `4:06` in the latest timeline.
- Do not use `photo_056_DJI_20000104170445_0011_D_t004_5.png`, `ST-617`, or `ST-616`; these correspond to the still images requested for cutting around `0:52`, `6:41`, and `11:05` in the latest rendered review.
- Do not use `ST-625` or `ST-635`; these have now been requested for cutting/deletion from the timeline.
- Do not use `photo_001_ST-600`, `photo_003_ST-604`, or `photo_005_ST-614`. Do not replace them just to maintain duration; the finished video may be about 15 seconds shorter.
- For the latest requested rebuild, exclude the original `a2ecf072-e001-453b-8432-780011ee6fea`, `DJI_20000104175108_0027_D`, and `DJI_20000104172535_0017_D` as well. The later exception clip `video_023_...clip56_89-114_43.mp4` remains allowed.

## Overall Output

- Build an emotional birthday highlight video.
- Target duration for the current preview/final render is recalculated from the fixed source ranges: exclude `video_004_DJI_20000104171531_0016_D.MP4`, `video_005_DJI_20000104172535_0017_D.MP4`, `video_018_0875db90-5d21-463d-b4b0-9f0a19195ca2.mp4`, and `video_022_ed5c2815-5ecc-4b02-ba3b-b0c8e02257fd.mp4`, add `video_001_DJI_20000104161921_0006_D.MP4` source `0:00-1:40` immediately after the opening title flower segment and before `ST-630`, cut the later `video_001_DJI_20000104161921_0006_D_clip_038_113` section that appeared around `4:10-5:20` in the latest full render, split `video_023_...clip56_89-114_43.mp4` into `0:00-0:15` and `0:15-0:40`, keep `ST-729` between those two split video pieces, and move `ST-730` to immediately after the second `video_023` piece `0:15-0:40`, add the two fixed middle clips from `video_014_ST7_8341.MP4`, keep the other requested `video_001_DJI_20000104161921_0006_D.MP4` fixed source ranges, replace `video_002_DJI_20000104164015_0007_D.MP4` with its requested fixed source range, replace `video_003_DJI_20000104171048_0015_D.MP4` with all source footage except `0:51-0:54`, split `video_006_DJI_20000104172624_0018_D.MP4` at the requested latest-full-render insertion points, place `ST-653` and `ST-686` consecutively with no video between them, split `video_012_DJI_20000104181624_0030_D.MP4` at source `0:54.96` and insert `ST-731` there, then continue into the second `video_012` piece and full `video_013_DJI_20000104181937_0031_D.MP4` before the final continuous still-photo block.
- Do not apply a global color grade, warm filter, contrast adjustment, brightness lift, saturation boost, or color-balance effect. Preserve the source colors to avoid black crush, blown highlights, and red-channel clipping.
- Keep the visual softness through transitions, fades, still-image motion, and the source material itself, not through color effects.
- Apply a soft dissolve transition wherever a still image touches another item: video-to-image, image-to-video, and image-to-image boundaries. The current target dissolve is about 0.65 seconds, capped so it never consumes too much of a short clip.
- Apply the normal soft dissolve from the opening `ST-707` title/flower segment into the inserted `video_001_DJI_20000104161921_0006_D_clip_000_100`.
- Keep direct video-to-video boundaries as normal cuts when they are intentionally connected video blocks.
- Produce a lightweight preview first with the Python build script before creating any heavier final render.
- The preview should be about 24 minutes 46 seconds. A small timing difference is acceptable if all content rules are satisfied.
- For normal previews, do not show the current source filename in the upper-left corner.
- Use `--show-source-labels` only when a source-identification review render is explicitly requested.
- Start the video on pure white. Fade in the large centered `Birthday` text and date gently, using three times the previous fade-in timing.
- Do not return to a plain white screen between the title text and the first flower image. While the title text dissolves away with three times the previous fade-out timing, reveal the original `ST-707` flower title image softly underneath it, then dissolve from the flower image into `video_001_DJI_20000104161921_0006_D.MP4` source `0:00-1:40`.
- After that inserted `video_001` opening clip, continue into `ST-630` and then put only still images that pass the strict no-face opening gate together at the beginning. The gate must use refreshed image analysis, not stale cache, and must exclude any image with a detected or high-confidence suspected human face.
- End the video with `ST-716.jpg`. Show the final image for the same duration as other normal still images, then fade the ending to white instead of black.
- Place `ST-709` around the 1-minute area. Do not include `ST-621`.
- Move `ST-738` and `ST-737` out of the opening area and place them between `video_003_DJI_20000104171048_0015_D_clip_054_end` and `video_014_ST7_8341_clip_000_046`. Keep `ST-737` immediately after `ST-738`.
- Place `ST-608` at a clean cut between 5 and 7 minutes.
- Keep `photo_049_ST-729` between `video_023_a2ecf072-e001-453b-8432-780011ee6fea_clip56_89-114_43` source `0:00-0:15` and source `0:15-0:40`. Move `photo_050_ST-730` to immediately after the second `video_023` piece, source `0:15-0:40`. Keep the normal dissolve effect at video-image, image-image, and image-video boundaries, and keep source video audio only on the video portions.
- Move `photo_038_ST-701`, `photo_039_ST-702`, and `photo_013_ST-628` to the early part of the timeline. Move `photo_018_ST-638` to immediately before `ST-667`.
- Move `photo_016_ST-634` out of the four-image block before `video_006`. Place it after `ST-618`, in the small two-image run between `video_002_DJI_20000104164015_0007_D.MP4` and `video_003_DJI_20000104171048_0015_D.MP4`.
- Move `ST-686` immediately after `ST-653`; do not place any video clip between `ST-653` and `ST-686`.
- Do not use `ST-676`.
- Keep the 7-minute still-image cluster to two images: `ST-608` and `ST-601`. Do not include `ST-617` or `ST-624`.
- Use `ST-688` immediately after `ST-723`. Keep `ST-699` in its current slot immediately after `ST-601`.
- Move `ST-661`, the still image that started around latest full-render `14:35`, so it starts around latest full-render `14:50`. To do this, split `video_006_DJI_20000104172624_0018_D.MP4` source `3:14.29-3:48.29` into `3:14.29-3:19.29` and `3:19.29-3:48.29`, and insert `ST-661` between those two pieces with the normal dissolve on both sides. Keep `ST-690` later after `ST-706`.
- Move `ST-668` and `ST-670` immediately after the final split piece of `video_006_DJI_20000104172624_0018_D.MP4`, in that order. Then keep `ST-677` immediately after `ST-670`, keep `ST-706` immediately after `ST-677`, and keep `ST-690` immediately after `ST-706`.
- Split the still-image cluster that appeared around `11:30` in the latest timeline. Keep `ST-632` in the later gap after `ST-667` before the connected `video_006_DJI_20000104172624_0018_D` block. Do not include `ST-616` or `ST-625`.
- Move `ST-670` immediately after `ST-668`; both now belong directly after the final split piece of `video_006_DJI_20000104172624_0018_D.MP4`.
- Move `ST-667` farther into the back half, immediately before the first split piece of `video_006_DJI_20000104172624_0018_D.MP4`, and keep it separated from its previous middle placement.
- Move `ST-646`, the still image at latest full-render `13:39`, into the cut immediately after the short video clip that originally followed it: place it between `video_006` source `1:22.29-1:27` and `2:11-2:33.29`. Insert `ST-653` into the same source video at the latest full-render `14:07` point, then show `ST-686` immediately after `ST-653` with no video between them.
- Move `ST-735` to immediately after `video_013_DJI_20000104181937_0031_D.MP4`.
- In the still-image block before the first split piece of `video_006_DJI_20000104172624_0018_D.MP4`, keep `ST-667`, `ST-632`, and `ST-675`. Do not keep `ST-634`, `ST-646`, `ST-653`, `ST-668`, or `ST-670` in this block; `ST-634` moves to the two-image `ST-618` / `ST-634` run before `video_003`, `ST-646` and `ST-653` are inserted into `video_006`, and `ST-668`/`ST-670` move to immediately after the final split piece of `video_006`.
- Swap the positions of `ST-725` and `ST-723`: place `ST-723` in the late video/photo gap after the second `video_023` piece; place `ST-725` in the final continuous photo block after `ST-713`.
- Render `ST-723` with the normal portrait still-image rule: keep it vertical with white side margins, not a manual full-width landscape crop.
- Move `photo_029_ST-682` and `photo_044_ST-713` to the beginning area of the final continuous still-photo block, in that order.
- Insert `ST-665` into `video_006_DJI_20000104172624_0018_D.MP4` at the latest full-render `15:15` insertion point by splitting the video.
- Place `ST-721` as the second-from-last still image by photo order, immediately before the final `ST-716` image.
- Do not use `ST-625`. Do not add a replacement photo just to fill the old slot.
- Move the videos that appeared around 10 to 14 minutes in the prior full render, `video_012_DJI_20000104181624_0030_D.MP4` and `video_013_DJI_20000104181937_0031_D.MP4`, to immediately before the final continuous still-photo block.
- Insert `ST-731` into `video_012_DJI_20000104181624_0030_D.MP4` at the position corresponding to latest full-render `20:01`. This maps to source `0:54.96`; split `video_012` into `0:00-0:54.96` and `0:54.96-end`, place `ST-731` between those two pieces, then continue into `video_013`.
- Spread `ST-601` across the timeline instead of letting it cluster in natural filename order. `ST-625` is excluded. `ST-618` is a manual swap image and should move to the former `ST-676/ST-690` area before `video_003`.
- When still images are placed between two unrelated video segments, do not leave exactly one still image between those videos. Exact manual split insertions into `video_006` are intentional single-image insertions and must not be auto-filled with a second image.
- Individual placement constraints override the no-face opening group. A no-face image must not be pulled into the opening group if it has a manual front-half, back-half, or distributed-placement rule.

## Video Selection

- Analyze every current source video before selecting clips.
- Apply the project exclusion list before video selection.
- Select impressive moments, but prioritize stable camera sections.
- Avoid parts where the camera is moving heavily, shaking, or panning too aggressively.
- Prefer moments where many people are visible.
- Use face/person position analysis when choosing the source-in point.
- Allocate video duration by analysis score for the 12-minute version: shrink lower-impression clips and preserve more time for stronger clips.
- For `video_001_DJI_20000104161921_0006_D.MP4`, use source `0:00-1:40` as an opening insert immediately after the title flower segment and before `ST-630`. Also keep fixed clip `6:27-9:14` later. Cut the later source `0:38-1:53` clip entirely; this was the `video_001` section around `4:10-5:20` in the latest full render, up to just before the next cut. Keep only the remaining later source `2:19-3:31` clip.
- Do not use `video_018_0875db90-5d21-463d-b4b0-9f0a19195ca2.mp4`.
- For `video_002_DJI_20000104164015_0007_D.MP4`, do not use the previously selected range. Use only the fixed clip `7:43-8:40`.
- For `video_006_DJI_20000104172624_0018_D.MP4`, do not use the previously excluded state or any analysis-selected range. Based on the prior full render, cut the first 1 second of the video, cut the full-render `11:05-11:49` section, cut the full-render `16:00-16:03` section, cut the full-render `17:08-17:12` section, and cut the short source range `2:33.29-2:38.29` so `ST-653` and `ST-686` can be shown consecutively. Use the fixed source ranges `0:01-0:48.29`, `0:48.29-1:22.29`, `1:22.29-1:27`, `2:11-2:33.29`, `2:38.29-2:57`, `3:04-3:14.29`, `3:14.29-3:19.29`, `3:19.29-3:48.29`, and `3:48.29-5:56`, inserting the requested still images between those pieces.
- Do not use `video_004_DJI_20000104171531_0016_D.MP4`.
- Do not use `video_005_DJI_20000104172535_0017_D.MP4`.
- Do not use `video_022_ed5c2815-5ecc-4b02-ba3b-b0c8e02257fd.mp4`; cut it completely from the timeline.
- Do not use `video_016_4e1e990e-0b3c-404c-9fb0-ef25073073ea.mp4` or `video_017_8ea3f1b6-af35-4c9b-9576-71eba58d9f5e.mp4`; these were the split video portions around `18:31-18:50` in the full preview. Keep the still images between them, including `photo_033_ST-694.jpg` and `photo_035_ST-697.jpg`.
- Do not use `video_019_503179b6-95c2-4918-8c7c-4efc3014d757.mp4`; this was the remaining `...757.mp4` source video around `18:35` in the labeled preview. Its previous role as the `ST-729` placement anchor must be removed so the video cannot return during source rescans.
- Move `video_012_DJI_20000104181624_0030_D.MP4`, the video that contained `21:46` in the full render, before full `video_013_DJI_20000104181937_0031_D.MP4`, the video that contained `11:13`. Split `video_012` at source `0:54.96`, insert `ST-731` between the split pieces, and continue directly into `video_013` before the final continuous still-photo block.
- Insert `video_023_a2ecf072-e001-453b-8432-780011ee6fea_clip56_89-114_43.mp4` into the back half of the timeline and use only its first 40 seconds (`0.00-40.00`), split as `0.00-15.00` and `15.00-40.00`; keep `ST-729` between the split parts and move `ST-730` immediately after the `15.00-40.00` part.
- Insert `video_014_ST7_8341.MP4` into the middle of the timeline as two separate clips: `0:00-0:46` first, then `3:37-3:53`. Place the `3:37-3:53` clip immediately after the `0:00-0:46` clip, with no still images or other media between those two `video_014` clips. Keep the combined `video_014` pair before the connected `video_006_DJI_20000104172624_0018_D.MP4` block.
- For `video_003_DJI_20000104171048_0015_D.MP4`, use the full source video except for source `0:51-0:54`. Keep the two remaining pieces connected with no photo or other media between them.
- Do not zoom video clips.
- Do not crop video clips for motion effects. Preserve the source video framing by scaling to fit the output frame and padding if needed.
- Cut clips from the original videos and play them normally.

## Still Image Selection

- Analyze all current images before rendering them.
- Deduplicate near-identical still images. Known current duplicate groups include `ST-645/ST-645w`, `ST-665/ST-665w`, `ST-721/ST-721w`, and `ST-716/ST-717w`.
- Exclude `ST-600`, `ST-604`, `ST-610`, `ST-614`, `ST-616`, `ST-617`, `ST-621`, `ST-624`, `ST-625`, `ST-635`, `ST-641` / `ST-641w`, `ST-676`, and `photo_056_DJI_20000104170445_0011_D_t004_5.png` before image ordering and deduplication.
- Preserve required images when deduplicating: keep `ST-716` as the final image, keep the title image, and keep manually placed images such as `ST-709`, `ST-737`, `ST-738`, `ST-638`, `ST-608`, `ST-682`, `ST-713`, `ST-628`, `ST-701`, `ST-702`, `ST-634`, `ST-690`, `ST-686`, `ST-723`, `ST-688`, `ST-731`, `ST-729`, `ST-730`, and `ST-645`.
- Display each normal still image for 5 seconds.
- The opening title segment is 15 seconds: it starts on pure white, the centered `Birthday` and date text fades in with three times the previous timing, then fades out with three times the previous timing while the original `ST-707` flower image fades in underneath it. Avoid a separate all-white beat between the text and the flower image. After that, dissolve from `ST-707` into `video_001_DJI_20000104161921_0006_D.MP4` source `0:00-1:40`, then continue to `ST-630`.
- The final still uses the same 5-second duration as other normal still images and fades to white at the end.
- Still-image transitions must not feel like hard cuts. Every still-image boundary should cross-dissolve softly into the previous or next visual item.
- Display portrait still images in their original vertical aspect ratio with white left and right margins, but never allow top or bottom gaps. Even at the smallest zoom scale, the portrait image must fill the full video height.
- For portrait still images, do not apply a warm/color grade to the photo area. Keep the original photo colors while keeping the left and right letterbox margins white.
- Keep the still-image motion and fade behavior on portrait still images: use the same one-direction zoom intent while keeping the image height at least as tall as the video frame, and apply a smooth white fade in/out at the beginning and end of the portrait still segment.
- For non-portrait still images whose aspect ratio does not match the output video aspect ratio, crop them to the video aspect ratio.
- When cropping non-portrait still images, first detect the subject area, draw a square around that subject area, and use the square center as the center point for the video-aspect-ratio crop.
- For faces, use the union of detected faces with padding as the subject area. The current script must run YuNet face detection plus Haar cascade fallback, store `faceDetection.noFaceOpeningEligible`, and use that flag for the opening no-face group instead of relying only on `personRelation.faceCount == 0`. If faces are not detected, use edge/saliency fallback to estimate the main subject.
- Add subtle but visible motion to every still image.
- Motion on a still image must be one direction only:
  - tiny zoom in,
  - tiny zoom out,
- or fade out if requested later.
- Do not pan still images.
- Do not make still-image motion go back and forth.
- Still-image zoom must move continuously for the full display duration. Do not ease in/out or hold still at the beginning or end.
- Keep still-image zoom slower than the earlier 5.5% motion; use a small linear zoom amount.
- Avoid shaky-looking still-image zooms; use smooth subpixel rendering.

## Audio

- Use `projects/260526-birthday/source/audio/audio_001_優しい気持ち.mp3` as the current background music source.
- Delete the previously generated/downloaded BGM source files from `projects/260526-birthday/source/audio`; keep only the current requested MP3 unless the user adds another source later.
- Loop and trim `audio_001_優しい気持ち.mp3` under the full preview.
- Play the BGM under the whole video.
- Whenever any source video segment is playing, lower BGM volume to 15% of the normal BGM level. If that segment has original video audio, raise the original video audio to 2x of the normal original-audio level, capped at 1.0.
- When still images are inserted between two split pieces of the same source video, keep the BGM at the same lowered video-segment level during those still images. Do not let the BGM return to normal volume just because the visible image is a still.
- Do not treat normal slideshow images as video-audio-focus images just because they happen to sit between two clips from the same original source video. In particular, the opening/front-half image slideshow before about 6 minutes must use the normal BGM level except during actual video segments.
- Do not switch that audio focus abruptly. Apply a smooth dissolve-style volume curve at each video segment start and end. Current transition: 1 second with a smoothstep curve.
- When two or more video segments are directly connected, or when split pieces of the same source video are separated only by inserted still images, merge those sections into one continuous audio-focus interval. Do not let the BGM rise between them and then duck again.
- The audio focus rule must be derived from every current timeline video segment and from the current manually inserted image runs between split pieces of the same source video, not fixed timestamps and not only videos with audio, so it remains active if videos or inserted images are moved earlier/later or newly added in future timeline changes.
- Fade the mixed audio in slowly at the start of the video and fade it out slowly at the end of the video. Current fade length: 5 seconds in and 5 seconds out.

## Current Script Behavior

- The preview output is generated by `projects/260526-birthday/scripts/build_event_highlight.py`.
- Use preview mode for lightweight review output:

```powershell
python .\projects\260526-birthday\scripts\build_event_highlight.py --project-root 'C:\Users\yurin\Desktop\video_edit\projects\260526-birthday' --preview --target-seconds 1486 --base-image-seconds 5 --background-audio 'source/audio/audio_001_優しい気持ち.mp3' --dedupe-images --force --jobs 2
```

- The current preview output path is `projects/260526-birthday/output/videos/260526-birthday-preview.mp4`.
- The timeline report is `projects/260526-birthday/output/reports/birthday_preview/birthday_preview_timeline.json`.
- The used video review clips are written to `projects/260526-birthday/output/used_video_parts_preview`.
- The used source images are copied to `projects/260526-birthday/output/used_images_preview`.
- The used media export manifest is `projects/260526-birthday/output/reports/birthday_preview/birthday_preview_used_media_exports.json`.

## Verification Checklist

- Confirm the source video count immediately before rendering.
- Confirm source files are not double-prefixed when re-running the source rename step.
- Confirm every video in the timeline still exists on disk.
- Confirm excluded video stems are absent from the timeline.
- Confirm excluded image stems such as `ST-600`, `ST-604`, `ST-610`, `ST-614`, `ST-616`, `ST-617`, `ST-621`, `ST-624`, `ST-641`, `ST-676`, and `photo_056_DJI_20000104170445_0011_D_t004_5.png` are absent from the timeline.
- Confirm no still images outside `source/phtp2605269` appear in the timeline.
- Confirm `ST-641` / `ST-641w` are absent from the timeline.
- Confirm no allowed current source videos were accidentally skipped unless the duration limit requires it.
- Confirm near-identical still images are deduplicated and required images such as `ST-716` are preserved.
- Confirm normal still images are exactly 5 seconds each.
- Confirm `visualTransitions` exists in the timeline report and includes every boundary where either side is a still image. Confirm direct video-to-video boundaries are not cross-dissolved unless an image is involved.
- Confirm no unrelated video-to-video break contains exactly one still image; exact manual split insertions inside `video_006` may contain one requested still image.
- Confirm `ST-729` is inserted between the split `video_023` clips, and confirm `ST-730` appears immediately after `video_023...clip_015_040`; confirm `ST-645` is no longer placed after `video_023`.
- Confirm `ST-736` is in the front half.
- Confirm `ST-701`, `ST-702`, and `ST-628` are in the early part of the timeline. Confirm `ST-638` appears immediately before `ST-667`.
- Confirm the 7-minute still-image cluster contains two images only: `ST-608` and `ST-601`.
- Confirm `ST-688` appears immediately after `ST-723`, and `ST-699` remains immediately after `ST-601` instead of in the opening no-face image group.
- Confirm `ST-723` appears in the late video/photo gap after the second `video_023` piece, and `ST-686` is no longer immediately after `ST-723`.
- Confirm `ST-634` appears after `ST-618` in the two-image run between `video_002_DJI_20000104164015_0007_D.MP4` and `video_003_DJI_20000104171048_0015_D.MP4`, not in the four-image block before `video_006`.
- Confirm `ST-676` is absent from the timeline.
- Confirm the still-image cluster around the prior `11:30` area is split: `ST-632` remains before the split `video_006` block, `ST-616` and `ST-625` are absent, `ST-661` is moved from the latest-full-render `14:35` position and inserted between `video_006...clip_194_3_199_3` and `video_006...clip_199_3_228_3` so it starts around latest full-render `14:50`, and `ST-690` moves after `ST-706`.
- Confirm `ST-618` appears in the former `ST-676/ST-690` area before `video_003_DJI_20000104171048_0015_D.MP4`, and confirm `ST-635` is absent.
- Confirm `ST-668` and `ST-670` appear immediately after the final split piece of `video_006_DJI_20000104172624_0018_D.MP4`, in that order.
- Confirm `ST-667` appears farther into the back half immediately before the first split piece of `video_006`.
- Confirm `ST-646` and `ST-653` are inserted into `video_006` at their requested latest-full-render positions, and confirm `ST-686` appears immediately after `ST-653` with no video between the two images.
- Confirm `ST-735` appears immediately after `video_013_DJI_20000104181937_0031_D.MP4`.
- Confirm the still-image block before the first split piece of `video_006` no longer contains `ST-634`, `ST-646`, `ST-653`, `ST-668`, or `ST-670`.
- Confirm `ST-725` is in the final continuous photo block after `ST-713`.
- Confirm `ST-723` uses the normal portrait still-image render mode with white side margins, not the previous manual landscape-crop override.
- Confirm `ST-682` and `ST-713` appear at the beginning area of the final continuous still-photo block, in that order.
- Confirm `ST-665` is inserted into `video_006` at the requested latest-full-render `15:15` position, not kept as the third-from-last still image.
- Confirm `ST-721` is the second-from-last still image by photo order, immediately before `ST-716`.
- Confirm `ST-625` is absent from the timeline.
- Confirm `video_004_DJI_20000104171531_0016_D.MP4` is absent from the timeline.
- Confirm `video_005_DJI_20000104172535_0017_D.MP4` is absent from the timeline.
- Confirm `video_022_ed5c2815-5ecc-4b02-ba3b-b0c8e02257fd.mp4` is absent from the timeline.
- Confirm `video_018_0875db90-5d21-463d-b4b0-9f0a19195ca2.mp4` is absent from the timeline.
- Confirm `video_016_4e1e990e-0b3c-404c-9fb0-ef25073073ea.mp4` and `video_017_8ea3f1b6-af35-4c9b-9576-71eba58d9f5e.mp4` are absent from the timeline while `photo_033_ST-694.jpg` and `photo_035_ST-697.jpg` remain present.
- Confirm `video_019_503179b6-95c2-4918-8c7c-4efc3014d757.mp4` is absent from the timeline, and confirm `ST-729` / `ST-730` remain present without using that deleted video as an anchor.
- Confirm `video_012_DJI_20000104181624_0030_D.MP4` appears as split source ranges `0:00-0:54.96` and `0:54.96-end`, with `ST-731` inserted between those two pieces and no `ST-686` inside it.
- Confirm the split `video_012_DJI_20000104181624_0030_D.MP4` block appears immediately before full `video_013_DJI_20000104181937_0031_D.MP4`.
- Confirm the `video_012` and `video_013` sequence appears immediately before the final continuous still-photo block, not around the 10 to 14 minute area.
- Confirm `video_006_DJI_20000104172624_0018_D.MP4` appears as split source ranges `0:01-0:48.29`, `0:48.29-1:22.29`, `1:22.29-1:27`, `2:11-2:33.29`, `2:38.29-2:57`, `3:04-3:14.29`, `3:14.29-3:19.29`, `3:19.29-3:48.29`, and `3:48.29-5:56`.
- Confirm `ST-645`, `ST-646`, `ST-653`, `ST-686`, `ST-661`, and `ST-665` are inserted between the requested `video_006` split pieces, with `ST-646` between `clip_082_3_087` and `clip_131_153_3`, `ST-653` and `ST-686` consecutive, and `ST-661` between `clip_194_3_199_3` and `clip_199_3_228_3`.
- Confirm `ST-668`, `ST-670`, `ST-677`, `ST-706`, and `ST-690` appear immediately after the final `video_006` split piece, in that order.
- Confirm `video_014_ST7_8341_clip_217_233` appears immediately after `video_014_ST7_8341_clip_000_046`, with no images or other media between those two clips, and that the pair appears before the connected `video_006` block.
- Confirm `ST-738` then `ST-737` appear between `video_003_DJI_20000104171048_0015_D_clip_054_end` and `video_014_ST7_8341_clip_000_046`, and are no longer in the opening image group.
- Confirm `video_023_a2ecf072-e001-453b-8432-780011ee6fea_clip56_89-114_43.mp4` is present in the back half as two split clips, `0.00-15.00` and `15.00-40.00`, with `ST-729` between the clips and `ST-730` immediately after `clip_015_040`.
- Confirm `video_003_DJI_20000104171048_0015_D.MP4` appears only as connected source ranges `0:00-0:51` and `0:54-end`, with no media between those pieces.
- Confirm `ST-601` is distributed across the timeline, `ST-625` is absent, and `ST-618` follows the requested swap placement.
- Confirm the opening starts on pure white, the large centered `Birthday` and date text appears with three times the previous timing, fades away with three times the previous timing, overlaps with the original `ST-707` flower image softly appearing from white, and then dissolves from `ST-707` into the inserted `video_001` opening clip.
- Confirm `video_001_DJI_20000104161921_0006_D_clip_000_100` appears immediately after the title screen and before `ST-630`.
- Confirm all still images immediately after the title card have `faceDetection.noFaceOpeningEligible == true`, and confirm no image with any detected human face is included in that opening group.
- Confirm the final visual item is `ST-716.jpg`, uses the normal still-image duration, and fades to white at the end.
- Confirm every still-image segment has one-way zoom metadata and visible movement.
- Confirm portrait still images have no top or bottom gaps at any point in their zoom/fade motion, have white left/right margins, and keep their fade in/out effect.
- Confirm no color grade is applied: videos, landscape stills, portrait still photo areas, and the `ST-707` flower image should preserve source color and avoid black crush, clipped whites, and blown reds, while portrait side margins remain white.
- Confirm generated segment/log folders do not contain stale files from old timelines before checking durations or motion modes.
- Confirm the final preview/render is about 24 minutes 46 seconds long.
- Confirm the output has both video and BGM-mixed audio.
- Confirm the timeline report has audio focus intervals derived from source video segments plus manually inserted still-image runs between split pieces of the same source video, with those video/image/video sections merged into continuous focus intervals, `focusMode == "video-segments-and-split-video-inserted-images"`, `focusMergeGapSeconds == 0.05`, and `focusCurve == "smoothstep"`. Confirm the normal front-half slideshow images before about 6 minutes are not included in a long audio-focus interval.
- Confirm normal previews do not show the source filename label in the upper-left corner.
- Confirm `used_video_parts_preview` and `used_images_preview` contain only current-timeline files with filenames based on the renamed source files.
- Run a full `ffmpeg -v error -i <output> -f null -` decode check before delivery.
