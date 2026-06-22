# 260526 Birthday Video Editing Instructions

## Source Handling

- Use the current files that exist under `projects/260526-birthday/source`.
- For still images, use only files under `projects/260526-birthday/source/phtp2605269`.
- Do not use still images from any other source subfolder, including the `todoroki260526...` folder.
- Add the extracted still `photo_056_DJI_20000104170445_0011_D_t004_5.png`, created from `C:\Users\yurin\Downloads\FOLDER01\DJI_20000104170445_0011_D.MP4` at 4.5 seconds, as a valid project still image under `source/phtp2605269`.
- Add the moved stills `photo_057_ST-686.jpg` and `photo_058_ST-723.jpg`, moved from `C:\Users\yurin\Downloads\FOLDER01`, as valid project still images under `source/phtp2605269`.
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
- Target duration for the current preview/final render is recalculated from the fixed source ranges: exclude `video_005_DJI_20000104172535_0017_D.MP4`, add the fixed 40-second `video_023_...clip56_89-114_43.mp4` source clip, add the two fixed middle clips from `video_014_ST7_8341.MP4`, replace `video_001_DJI_20000104161921_0006_D.MP4` with its two requested fixed source ranges, replace `video_002_DJI_20000104164015_0007_D.MP4` with its requested fixed source range, add `video_006_DJI_20000104172624_0018_D.MP4` as a fixed source range, and connect full `video_012_DJI_20000104181624_0030_D.MP4` followed by full `video_013_DJI_20000104181937_0031_D.MP4`.
- Use a soft, consistent color grade across videos and still images.
- Keep the final look gentle and warm rather than high-contrast or heavily saturated.
- Produce a lightweight preview first with the Python build script before creating any heavier final render.
- The preview should be about 24 minutes 41 seconds. A small timing difference is acceptable if all content rules are satisfied.
- For normal previews, do not show the current source filename in the upper-left corner.
- Use `--show-source-labels` only when a source-identification review render is explicitly requested.
- Start the video with `ST-707bg` if present, otherwise use `ST-707.jpg`. This opening card must be 5 seconds, have no animation, and include a gentle home-birthday style title with the date and birthday wording in the upper-right corner.
- After the title card, put only still images that pass the strict no-face opening gate together at the beginning. The gate must use refreshed image analysis, not stale cache, and must exclude any image with a detected or high-confidence suspected human face.
- End the video with `ST-716.jpg`. Show the image without animation for 5 seconds, then fade to black over 5 seconds.
- Place `ST-621` and `ST-709` consecutively around the 1-minute area.
- Place `ST-737` immediately after `ST-738` as an exception, even though `ST-737` contains a person.
- Place `ST-608` at a clean cut between 5 and 7 minutes.
- Move `photo_049_ST-729`, `photo_050_ST-730`, and `photo_019_ST-645` into late inter-video gaps. Place `ST-729` after `video_019_503179b6-95c2-4918-8c7c-4efc3014d757`, `ST-730` after `video_022_ed5c2815-5ecc-4b02-ba3b-b0c8e02257fd`, and `ST-645` after `video_023_a2ecf072-e001-453b-8432-780011ee6fea_clip56_89-114_43`, before the connected final video block.
- Place `ST-736`, `ST-735`, and `ST-731` in the front half of the timeline.
- Move `photo_038_ST-701`, `photo_039_ST-702`, `photo_018_ST-638`, and `photo_013_ST-628` to the early part of the timeline.
- Insert `photo_056_DJI_20000104170445_0011_D_t004_5.png` near the beginning of the video, before the first source-video clip if the current opening sequence timing allows it.
- Move `photo_016_ST-634`, `photo_028_ST-676`, and `photo_031_ST-690` to the back half of the timeline.
- Insert `photo_057_ST-686` and `photo_058_ST-723` around the transition area between the middle and back half of the timeline, before the later back-half still group.
- Move `ST-667` and `ST-670` into the back half of the timeline and keep them separated from each other.
- Move `photo_029_ST-682` and `photo_044_ST-713` to the beginning area of the final continuous still-photo block, in that order.
- Place `ST-665` as the third-from-last still image by photo order.
- Place `ST-721` as the second-from-last still image by photo order, immediately before the final `ST-716` image.
- Move `ST-625` earlier than the final video/photo area. Do not add a replacement photo just to fill the old late slot.
- Spread `ST-601`, `ST-617`, `ST-618`, and `ST-625` across the timeline instead of letting them cluster in natural filename order.
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
- For `video_006_DJI_20000104172624_0018_D.MP4`, do not use the previously excluded state or any analysis-selected range. Use only the fixed clip `0:00-5:56`.
- Do not use `video_005_DJI_20000104172535_0017_D.MP4`.
- Use full `video_012_DJI_20000104181624_0030_D.MP4`, then full `video_013_DJI_20000104181937_0031_D.MP4`, in that order, as a connected video block with no still images or other videos between them.
- Insert `video_023_a2ecf072-e001-453b-8432-780011ee6fea_clip56_89-114_43.mp4` into the back half of the timeline and use only its first 40 seconds (`0.00-40.00`).
- Insert `video_014_ST7_8341.MP4` into the middle of the timeline as two separate clips: `0:00-0:46` first, then `3:37-3:53`.
- For `video_003_DJI_20000104171048_0015_D.MP4`, cut the last 7 seconds from the selected clip. Keep the clip start point unchanged and shorten only the clip end.
- Do not zoom video clips.
- Do not crop video clips for motion effects. Preserve the source video framing by scaling to fit the output frame and padding if needed.
- Cut clips from the original videos and play them normally.

## Still Image Selection

- Analyze all current images before rendering them.
- Deduplicate near-identical still images. Known current duplicate groups include `ST-645/ST-645w`, `ST-665/ST-665w`, `ST-721/ST-721w`, and `ST-716/ST-717w`.
- Exclude `ST-600`, `ST-604`, `ST-610`, `ST-614`, and `ST-641` / `ST-641w` before image ordering and deduplication.
- Preserve required images when deduplicating: keep `ST-716` as the final image, keep the title image, and keep manually placed images such as `ST-621`, `ST-709`, `ST-737`, `ST-738`, `ST-638`, `ST-608`, `ST-682`, `ST-713`, `ST-628`, `ST-701`, `ST-702`, `ST-634`, `ST-676`, `ST-690`, `ST-686`, `ST-723`, `ST-729`, `ST-730`, `ST-645`, and `photo_056_DJI_20000104170445_0011_D_t004_5.png`.
- Display each normal still image for 5 seconds.
- The opening title still is 5 seconds with no zoom.
- The final still is 10 seconds total: 5 seconds static, then 5 seconds fading to black.
- Do not crop portrait still images. Display portrait still images in their original vertical aspect ratio, fit the full image inside the video frame, and fill the left and right margins with white.
- Keep the still-image motion and fade behavior on portrait still images: use the same one-direction zoom intent without cropping any part of the image, and apply a smooth white fade in/out at the beginning and end of the portrait still segment.
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
- Whenever any source video segment is playing, lower BGM volume to 50% of the normal BGM level. If that segment has original video audio, raise the original video audio to 2x of the normal original-audio level, capped at 1.0.
- Do not switch that audio focus abruptly. Apply a smooth dissolve-style volume curve at each video segment start and end. Current transition: 1 second with a smoothstep curve.
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
- Confirm excluded image stems such as `ST-600`, `ST-604`, `ST-610`, `ST-614`, and `ST-641` are absent from the timeline.
- Confirm no still images outside `source/phtp2605269` appear in the timeline.
- Confirm `ST-641` / `ST-641w` are absent from the timeline.
- Confirm no allowed current source videos were accidentally skipped unless the duration limit requires it.
- Confirm near-identical still images are deduplicated and required images such as `ST-716` are preserved.
- Confirm normal still images are exactly 5 seconds each.
- Confirm `ST-729`, `ST-730`, and `ST-645` are in the requested late inter-video gaps, before the connected final video block.
- Confirm `ST-736`, `ST-735`, and `ST-731` are in the front half.
- Confirm `ST-701`, `ST-702`, `ST-638`, and `ST-628` are in the early part of the timeline.
- Confirm `photo_056_DJI_20000104170445_0011_D_t004_5.png` appears near the beginning of the timeline.
- Confirm `ST-686` and `ST-723` appear around the transition area between the middle and back half of the timeline.
- Confirm `ST-634`, `ST-676`, and `ST-690` are in the back half of the timeline.
- Confirm `ST-667` and `ST-670` are in the back half and separated.
- Confirm `ST-682` and `ST-713` appear at the beginning area of the final continuous still-photo block, in that order.
- Confirm `ST-665` is the third-from-last still image by photo order.
- Confirm `ST-721` is the second-from-last still image by photo order, immediately before `ST-716`.
- Confirm `ST-625` has been moved earlier than the final video/photo area.
- Confirm `video_005_DJI_20000104172535_0017_D.MP4` is absent from the timeline.
- Confirm full `video_012_DJI_20000104181624_0030_D.MP4` is immediately followed by full `video_013_DJI_20000104181937_0031_D.MP4` with no media between them.
- Confirm `video_023_a2ecf072-e001-453b-8432-780011ee6fea_clip56_89-114_43.mp4` is present in the back half and has `manualFixedClip.fixedDuration == 40.0` with `sourceIn == 0.0`.
- Confirm `video_003_DJI_20000104171048_0015_D.MP4` has `manualEndTrim.trimmedSeconds == 7.0` in the timeline report and that its selected clip end is 7 seconds earlier than before.
- Confirm `ST-601`, `ST-617`, `ST-618`, and `ST-625` are distributed across the timeline.
- Confirm the opening title card is `ST-707bg` or `ST-707.jpg`, has no animation, and includes a clear modern date plus birthday title in the upper-right corner.
- Confirm all still images immediately after the title card have `faceDetection.noFaceOpeningEligible == true`, and confirm no image with any detected human face is included in that opening group.
- Confirm the final visual item is `ST-716.jpg`, 10 seconds total: 5 seconds static plus 5 seconds slow fade to black.
- Confirm every still-image segment has one-way zoom metadata and visible movement.
- Confirm portrait still images are not cropped, have white left/right margins, and keep their fade in/out effect.
- Confirm generated segment/log folders do not contain stale files from old timelines before checking durations or motion modes.
- Confirm the final preview/render is about 24 minutes 41 seconds long.
- Confirm the output has both video and BGM-mixed audio.
- Confirm the timeline report has audio focus intervals for every source video segment, with `focusMode == "all-video-segments"` and `focusCurve == "smoothstep"`.
- Confirm normal previews do not show the source filename label in the upper-left corner.
- Confirm `used_video_parts_preview` and `used_images_preview` contain only current-timeline files with filenames based on the renamed source files.
- Run a full `ffmpeg -v error -i <output> -f null -` decode check before delivery.
