# 260526 Birthday Video Editing Instructions

## Source Handling

- Use the current files that exist under `projects/260526-birthday/source`.
- For still images, use only files under `projects/260526-birthday/source/phtp2605269`.
- Do not use still images from any other source subfolder, including the `todoroki260526...` folder.
- Add the extracted still `photo_056_DJI_20000104170445_0011_D_t004_5.png`, created from `C:\Users\yurin\Downloads\FOLDER01\DJI_20000104170445_0011_D.MP4` at 4.5 seconds, as a valid project still image under `source/phtp2605269`.
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
  - `0875db90-5d21-463d-b4b0-9f0a19195ca2`
  - `a2ecf072-e001-453b-8432-780011ee6fea`
  - `e6eeaf64-3602-4238-af85-8ccfc6701205`
  - `4e1e990e-0b3c-404c-9fb0-ef25073073ea`
  - `8ea3f1b6-af35-4c9b-9576-71eba58d9f5e`
  - `503179b6-95c2-4918-8c7c-4efc3014d757`
- Exception: use the newly moved source clip `source/video/video_023_a2ecf072-e001-453b-8432-780011ee6fea_clip56_89-114_43.mp4`. This is a trimmed review clip supplied later by the user, not the excluded original `video_020_a2ecf072-e001-453b-8432-780011ee6fea.mp4`.
- Exception: use `source/mp4/video_014_ST7_8341.MP4` only as two fixed middle timeline clips: `0:00-0:46` and `3:37-3:53`. Do not use any other part of `ST7_8341`.
- After excluding those videos, stretch the remaining videos to maintain the target duration. Use the video-analysis selected sample time and top visual/person-scored moments as the center of the longer clip, instead of extending arbitrary parts.
- It is acceptable to omit some videos if the timeline would exceed 15 minutes, but use the available videos and images as evenly as possible.
- Use the current still images, but do not repeat near-identical photos. Detect visually duplicated stills with perceptual hashing and keep the best-looking one from each duplicate group.
- Do not use still image `ST-610`.
- Do not use `ST-641` / `ST-641w`.
- Do not use `photo_001_ST-600`, `photo_003_ST-604`, or `photo_005_ST-614`. Do not replace them just to maintain duration; the finished video may be about 15 seconds shorter.
- For the latest requested rebuild, exclude the original `a2ecf072-e001-453b-8432-780011ee6fea`, `DJI_20000104175108_0027_D`, and `DJI_20000104172535_0017_D` as well. The later exception clip `video_023_...clip56_89-114_43.mp4` remains allowed.

## Overall Output

- Build an emotional birthday highlight video.
- Target duration for the current preview/final render is recalculated from the fixed source ranges: exclude `video_004_DJI_20000104171531_0016_D.MP4`, `video_005_DJI_20000104172535_0017_D.MP4`, and `video_022_ed5c2815-5ecc-4b02-ba3b-b0c8e02257fd.mp4`, add the fixed 40-second `video_023_...clip56_89-114_43.mp4` source clip, add the two fixed middle clips from `video_014_ST7_8341.MP4`, replace `video_001_DJI_20000104161921_0006_D.MP4` with its two requested fixed source ranges, replace `video_002_DJI_20000104164015_0007_D.MP4` with its requested fixed source range, replace `video_003_DJI_20000104171048_0015_D.MP4` with all source footage except `0:51-0:54`, add `video_006_DJI_20000104172624_0018_D.MP4` as fixed source ranges with requested cuts, and move full `video_012_DJI_20000104181624_0030_D.MP4` plus full `video_013_DJI_20000104181937_0031_D.MP4` to immediately before the final continuous still-photo block, in that order.
- Use a soft, consistent color grade across videos and still images.
- Keep the final look gentle and warm rather than high-contrast or heavily saturated.
- Produce a lightweight preview first with the Python build script before creating any heavier final render.
- The preview should be about 24 minutes 41 seconds. A small timing difference is acceptable if all content rules are satisfied.
- For normal previews, do not show the current source filename in the upper-left corner.
- Use `--show-source-labels` only when a source-identification review render is explicitly requested.
- Start the video with `ST-707bg` if present, otherwise use `ST-707.jpg`. This opening card must be 5 seconds, have no animation, and include a gentle home-birthday style title with the date and birthday wording in the upper-right corner.
- After the title card, put only still images that pass the strict no-face opening gate together at the beginning. The gate must use refreshed image analysis, not stale cache, and must exclude any image with a detected or high-confidence suspected human face.
- End the video with `ST-716.jpg`. Show the final image for three times the previous duration: 30 seconds total, with 15 seconds static and then 15 seconds fading to black.
- Place `ST-621` and `ST-709` consecutively around the 1-minute area.
- Place `ST-737` immediately after `ST-738` as an exception, even though `ST-737` contains a person.
- Place `ST-608` at a clean cut between 5 and 7 minutes.
- Move `photo_049_ST-729`, `photo_050_ST-730`, and `photo_019_ST-645` into late inter-video gaps. Since `video_019_503179b6-95c2-4918-8c7c-4efc3014d757.mp4` is no longer used, place `ST-729` after `ST-697`, place `ST-730` immediately after `ST-729`, and place `ST-645` after `video_023_a2ecf072-e001-453b-8432-780011ee6fea_clip56_89-114_43`, before the connected final video block.
- Move `ST-627` and `ST-736` from the earlier six-photo cluster into the photo gap between the connected `video_014_ST7_8341` pair and the connected `video_006_DJI_20000104172624_0018_D` block, filling the slots opened by moving `ST-661` and `ST-690` later. Keep `ST-627` immediately before `ST-736`.
- Move `photo_038_ST-701`, `photo_039_ST-702`, `photo_018_ST-638`, and `photo_013_ST-628` to the early part of the timeline.
- Insert `photo_056_DJI_20000104170445_0011_D_t004_5.png` near the beginning of the video, before the first source-video clip if the current opening sequence timing allows it.
- Move `photo_016_ST-634` out of the 7-minute still-image cluster and into the later back-half group.
- Move the still image that appeared at `4:02` in the latest labeled preview, `ST-616`, out of the 7-minute still-image cluster and into the next later still-image break after `ST-625`.
- Move the still image that appeared at `6:52` in the latest labeled preview, `ST-686`, to the late/end area after `ST-725`.
- Do not use `ST-676`.
- Keep the 7-minute still-image cluster to four images: `ST-608`, `ST-617`, `ST-601`, and `ST-624`.
- Move `ST-661` and `ST-690` one video later, to immediately after the connected `video_006_DJI_20000104172624_0018_D` block. Keep `ST-690` immediately after `ST-661`.
- Move `ST-677` to immediately after `video_006_DJI_20000104172624_0018_D_clip_184_356.MP4`, then keep `ST-706` immediately after `ST-677`.
- Split the still-image cluster that appeared around `11:30` in the latest timeline. Keep `ST-625` before `video_014_ST7_8341_clip_000_046`; move `ST-627` and `ST-736` from the earlier crowded image group into the old `ST-661` / `ST-690` area; keep `ST-632` after `ST-736` before the connected `video_006_DJI_20000104172624_0018_D` block.
- Move `ST-670` immediately after `ST-668`.
- Move `ST-667` farther into the back half, after `ST-735`, and keep it separated from its previous middle placement.
- Move the two still images around `9:13` in the prior full render, `ST-646` and `ST-653`, to the back half after `ST-670`.
- Move the still image that appeared at `4:13` in the prior full render, `ST-735`, to the back half after `ST-653`.
- Move the still image that appeared at `6:55` in the prior full render, `ST-723`, into the final continuous photo block after `ST-713` and before the last three-photo ending sequence.
- Move `photo_029_ST-682` and `photo_044_ST-713` to the beginning area of the final continuous still-photo block, in that order.
- Place `ST-665` as the third-from-last still image by photo order.
- Place `ST-721` as the second-from-last still image by photo order, immediately before the final `ST-716` image.
- Move `ST-625` earlier than the final video/photo area. Do not add a replacement photo just to fill the old late slot.
- Move the videos that appeared around 10 to 14 minutes in the prior full render, `video_012_DJI_20000104181624_0030_D.MP4` and `video_013_DJI_20000104181937_0031_D.MP4`, to immediately before the final continuous still-photo block.
- Move `ST-731` to immediately before `video_012_DJI_20000104181624_0030_D.MP4`.
- Spread `ST-601`, `ST-617`, and `ST-625` across the timeline instead of letting them cluster in natural filename order. `ST-618` is a manual swap image and should move to the former `ST-676/ST-690` area before `video_003`.
- When still images are placed between two video segments, do not leave exactly one still image between those videos. Move a nearby regular still image into that break so every image break between videos has at least two still images, while preserving connected video blocks.
- Individual placement constraints override the no-face opening group. A no-face image must not be pulled into the opening group if it has a manual front-half, back-half, or distributed-placement rule.

## Video Selection

- Analyze every current source video before selecting clips.
- Apply the project exclusion list before video selection.
- Select impressive moments, but prioritize stable camera sections.
- Avoid parts where the camera is moving heavily, shaking, or panning too aggressively.
- Prefer moments where many people are visible.
- Use face/person position analysis when choosing the source-in point.
- Allocate video duration by analysis score for the 12-minute version: shrink lower-impression clips and preserve more time for stronger clips.
- For `video_001_DJI_20000104161921_0006_D.MP4`, do not use the previously selected range. Use fixed clip `6:27-9:14` first. For the requested `0:38-3:31` clip, cut out the part that appeared at `5:47-6:13` in the full render; this corresponds to source `1:53-2:19`, so use `0:38-1:53` immediately followed by `2:19-3:31` with no photo or other media between those two pieces.
- For `video_002_DJI_20000104164015_0007_D.MP4`, do not use the previously selected range. Use only the fixed clip `7:43-8:40`.
- For `video_006_DJI_20000104172624_0018_D.MP4`, do not use the previously excluded state or any analysis-selected range. Based on the prior full render, cut the first 1 second of the video, cut the full-render `11:05-11:49` section, cut the full-render `16:00-16:03` section, and cut the full-render `17:08-17:12` section. Use source ranges `0:01-1:27`, `2:11-2:57`, and `3:04-5:56` with no photo or other media between those pieces.
- Do not use `video_004_DJI_20000104171531_0016_D.MP4`.
- Do not use `video_005_DJI_20000104172535_0017_D.MP4`.
- Do not use `video_022_ed5c2815-5ecc-4b02-ba3b-b0c8e02257fd.mp4`; cut it completely from the timeline.
- Do not use `video_016_4e1e990e-0b3c-404c-9fb0-ef25073073ea.mp4` or `video_017_8ea3f1b6-af35-4c9b-9576-71eba58d9f5e.mp4`; these were the split video portions around `18:31-18:50` in the full preview. Keep the still images between them, including `photo_033_ST-694.jpg` and `photo_035_ST-697.jpg`.
- Do not use `video_019_503179b6-95c2-4918-8c7c-4efc3014d757.mp4`; this was the remaining `...757.mp4` source video around `18:35` in the labeled preview. Its previous role as the `ST-729` placement anchor must be removed so the video cannot return during source rescans.
- Move full `video_012_DJI_20000104181624_0030_D.MP4`, the video that contained `21:46` in the full render, before full `video_013_DJI_20000104181937_0031_D.MP4`, the video that contained `11:13`. Keep these two videos immediately before the final continuous still-photo block.
- Insert `video_023_a2ecf072-e001-453b-8432-780011ee6fea_clip56_89-114_43.mp4` into the back half of the timeline and use only its first 40 seconds (`0.00-40.00`).
- Insert `video_014_ST7_8341.MP4` into the middle of the timeline as two separate clips: `0:00-0:46` first, then `3:37-3:53`. Place the `3:37-3:53` clip immediately after the `0:00-0:46` clip, with no still images or other media between those two `video_014` clips. Keep the combined `video_014` pair before the connected `video_006_DJI_20000104172624_0018_D.MP4` block.
- For `video_003_DJI_20000104171048_0015_D.MP4`, use the full source video except for source `0:51-0:54`. Keep the two remaining pieces connected with no photo or other media between them.
- Do not zoom video clips.
- Do not crop video clips for motion effects. Preserve the source video framing by scaling to fit the output frame and padding if needed.
- Cut clips from the original videos and play them normally.

## Still Image Selection

- Analyze all current images before rendering them.
- Deduplicate near-identical still images. Known current duplicate groups include `ST-645/ST-645w`, `ST-665/ST-665w`, `ST-721/ST-721w`, and `ST-716/ST-717w`.
- Exclude `ST-600`, `ST-604`, `ST-610`, `ST-614`, `ST-641` / `ST-641w`, and `ST-676` before image ordering and deduplication.
- Preserve required images when deduplicating: keep `ST-716` as the final image, keep the title image, and keep manually placed images such as `ST-621`, `ST-709`, `ST-737`, `ST-738`, `ST-638`, `ST-608`, `ST-682`, `ST-713`, `ST-628`, `ST-701`, `ST-702`, `ST-634`, `ST-690`, `ST-686`, `ST-723`, `ST-729`, `ST-730`, `ST-645`, and `photo_056_DJI_20000104170445_0011_D_t004_5.png`.
- Display each normal still image for 5 seconds.
- The opening title still is 5 seconds with no zoom.
- The final still is 30 seconds total: 15 seconds static, then 15 seconds fading to black.
- Display portrait still images in their original vertical aspect ratio with white left and right margins, but never allow top or bottom gaps. Even at the smallest zoom scale, the portrait image must fill the full video height.
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
- Do not switch that audio focus abruptly. Apply a smooth dissolve-style volume curve at each video segment start and end. Current transition: 1 second with a smoothstep curve.
- When two or more video segments are directly connected with no still image or other visible gap between them, merge those video segments into one continuous audio-focus interval. Do not let the BGM rise between connected video segments and then duck again.
- The audio focus rule must be derived from every current timeline video segment, not fixed timestamps and not only videos with audio, so it remains active if videos are moved earlier/later or newly added in future timeline changes.
- Fade the mixed audio in slowly at the start of the video and fade it out slowly at the end of the video. Current fade length: 5 seconds in and 5 seconds out.

## Current Script Behavior

- The preview output is generated by `projects/260526-birthday/scripts/build_event_highlight.py`.
- Use preview mode for lightweight review output:

```powershell
python .\projects\260526-birthday\scripts\build_event_highlight.py --project-root 'C:\Users\yurin\Desktop\video_edit\projects\260526-birthday' --preview --target-seconds 705 --base-image-seconds 5 --background-audio 'source/audio/audio_001_優しい気持ち.mp3' --dedupe-images --force --jobs 2
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
- Confirm excluded image stems such as `ST-600`, `ST-604`, `ST-610`, `ST-614`, `ST-641`, and `ST-676` are absent from the timeline.
- Confirm no still images outside `source/phtp2605269` appear in the timeline.
- Confirm `ST-641` / `ST-641w` are absent from the timeline.
- Confirm no allowed current source videos were accidentally skipped unless the duration limit requires it.
- Confirm near-identical still images are deduplicated and required images such as `ST-716` are preserved.
- Confirm normal still images are exactly 5 seconds each.
- Confirm no video-to-video break contains exactly one still image; every still-image break between videos must contain at least two still images.
- Confirm `ST-729`, `ST-730`, and `ST-645` are in the requested late inter-video gaps, before the connected final video block.
- Confirm `ST-736` is in the front half.
- Confirm `ST-627` and `ST-736` fill the former `ST-661` / `ST-690` area between the connected `video_014` pair and the connected `video_006` block, with `ST-627` immediately before `ST-736`.
- Confirm `ST-701`, `ST-702`, `ST-638`, and `ST-628` are in the early part of the timeline.
- Confirm `photo_056_DJI_20000104170445_0011_D_t004_5.png` appears near the beginning of the timeline.
- Confirm the 7-minute still-image cluster contains four images only: `ST-608`, `ST-617`, `ST-601`, and `ST-624`.
- Confirm `ST-616` appears outside that 7-minute cluster, after `ST-625`.
- Confirm `ST-686` appears in the late/end area after `ST-725`.
- Confirm `ST-634` is in the back half of the timeline.
- Confirm `ST-676` is absent from the timeline.
- Confirm the still-image cluster around the prior `11:30` area is split: `ST-625` remains before `video_014_ST7_8341_clip_000_046`, `ST-627` and `ST-736` fill the former `ST-661` / `ST-690` area, `ST-632` remains before the connected `video_006` block, and `ST-661` plus `ST-690` move immediately after the connected `video_006` block.
- Confirm `ST-618` and `ST-635` appear in the former `ST-676/ST-690` area before `video_003_DJI_20000104171048_0015_D.MP4`.
- Confirm `ST-670` appears immediately after `ST-668`.
- Confirm `ST-667` appears farther into the back half after `ST-735`.
- Confirm `ST-646` and `ST-653` are in the back half after `ST-670`.
- Confirm `ST-735` is in the back half after `ST-653`.
- Confirm `ST-723` is in the final continuous photo block after `ST-713` and before `ST-665`.
- Confirm `ST-682` and `ST-713` appear at the beginning area of the final continuous still-photo block, in that order.
- Confirm `ST-665` is the third-from-last still image by photo order.
- Confirm `ST-721` is the second-from-last still image by photo order, immediately before `ST-716`.
- Confirm `ST-625` has been moved earlier than the final video/photo area.
- Confirm `video_004_DJI_20000104171531_0016_D.MP4` is absent from the timeline.
- Confirm `video_005_DJI_20000104172535_0017_D.MP4` is absent from the timeline.
- Confirm `video_022_ed5c2815-5ecc-4b02-ba3b-b0c8e02257fd.mp4` is absent from the timeline.
- Confirm `video_016_4e1e990e-0b3c-404c-9fb0-ef25073073ea.mp4` and `video_017_8ea3f1b6-af35-4c9b-9576-71eba58d9f5e.mp4` are absent from the timeline while `photo_033_ST-694.jpg` and `photo_035_ST-697.jpg` remain present.
- Confirm `video_019_503179b6-95c2-4918-8c7c-4efc3014d757.mp4` is absent from the timeline, and confirm `ST-729` / `ST-730` remain present without using that deleted video as an anchor.
- Confirm `ST-731` appears immediately before full `video_012_DJI_20000104181624_0030_D.MP4`.
- Confirm full `video_012_DJI_20000104181624_0030_D.MP4` appears immediately before full `video_013_DJI_20000104181937_0031_D.MP4`.
- Confirm full `video_012_DJI_20000104181624_0030_D.MP4` and full `video_013_DJI_20000104181937_0031_D.MP4` appear immediately before the final continuous still-photo block, not around the 10 to 14 minute area.
- Confirm `video_006_DJI_20000104172624_0018_D.MP4` appears only as connected source ranges `0:01-1:27`, `2:11-2:57`, and `3:04-5:56`, with no media between those pieces.
- Confirm `ST-677` appears immediately after `video_006_DJI_20000104172624_0018_D_clip_184_356.MP4`, and `ST-706` appears immediately after `ST-677`.
- Confirm `video_014_ST7_8341_clip_217_233` appears immediately after `video_014_ST7_8341_clip_000_046`, with no images or other media between those two clips, and that the pair appears before the connected `video_006` block.
- Confirm `video_023_a2ecf072-e001-453b-8432-780011ee6fea_clip56_89-114_43.mp4` is present in the back half and has `manualFixedClip.fixedDuration == 40.0` with `sourceIn == 0.0`.
- Confirm `video_003_DJI_20000104171048_0015_D.MP4` appears only as connected source ranges `0:00-0:51` and `0:54-end`, with no media between those pieces.
- Confirm `ST-601`, `ST-617`, and `ST-625` are distributed across the timeline, while `ST-618` follows the requested swap placement.
- Confirm the opening title card is `ST-707bg` or `ST-707.jpg`, has no animation, and includes a clear modern date plus birthday title in the upper-right corner.
- Confirm all still images immediately after the title card have `faceDetection.noFaceOpeningEligible == true`, and confirm no image with any detected human face is included in that opening group.
- Confirm the final visual item is `ST-716.jpg`, 30 seconds total: 15 seconds static plus 15 seconds slow fade to black.
- Confirm every still-image segment has one-way zoom metadata and visible movement.
- Confirm portrait still images have no top or bottom gaps at any point in their zoom/fade motion, have white left/right margins, and keep their fade in/out effect.
- Confirm generated segment/log folders do not contain stale files from old timelines before checking durations or motion modes.
- Confirm the final preview/render is about 23 minutes 56 seconds long.
- Confirm the output has both video and BGM-mixed audio.
- Confirm the timeline report has audio focus intervals derived from every source video segment, with directly connected video segments merged into continuous focus intervals, `focusMode == "all-video-segments"`, `focusMergeGapSeconds == 0.05`, and `focusCurve == "smoothstep"`.
- Confirm normal previews do not show the source filename label in the upper-left corner.
- Confirm `used_video_parts_preview` and `used_images_preview` contain only current-timeline files with filenames based on the renamed source files.
- Run a full `ffmpeg -v error -i <output> -f null -` decode check before delivery.
