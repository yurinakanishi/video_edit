from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw


LIBRARY_ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATH = LIBRARY_ROOT / "output" / "reports" / "reference_assets_manifest.json"
MEDIA_MANIFEST_PATH = LIBRARY_ROOT / "output" / "reports" / "media_manifest.json"
SCHEMA_PATH = LIBRARY_ROOT / "config" / "reference_asset_analysis.schema.json"
QA_REPORT_PATH = LIBRARY_ROOT / "output" / "reports" / "qa_report.json"
CONTACT_SHEET_PATH = LIBRARY_ROOT / "output" / "reports" / "contact_sheets" / "qa_contact_sheet.jpg"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def validate_with_schema(payload: dict[str, Any], schema: dict[str, Any]) -> list[str]:
    try:
        import jsonschema

        jsonschema.validate(payload, schema)
        return []
    except ImportError:
        return manual_schema_checks(payload)
    except Exception as error:
        return [str(error)]


def manual_schema_checks(payload: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if payload.get("schemaVersion") != "reference-asset-analysis/v1":
        errors.append("schemaVersion must be reference-asset-analysis/v1")
    for key in ("asset", "summary", "frames"):
        if key not in payload:
            errors.append(f"missing {key}")
    asset = payload.get("asset")
    if not isinstance(asset, dict):
        errors.append("asset must be an object")
    else:
        for key in ("assetId", "collection", "kind", "sourcePath", "originalPath", "sha256", "sizeBytes"):
            if key not in asset:
                errors.append(f"asset missing {key}")
    frames = payload.get("frames")
    if not isinstance(frames, list) or not frames:
        errors.append("frames must be a non-empty array")
    else:
        for index, frame in enumerate(frames):
            if not isinstance(frame, dict):
                errors.append(f"frames[{index}] must be an object")
                continue
            for key in ("frameId", "timeSeconds", "width", "height", "people", "faces", "textOverlays", "logos", "annotations", "composition", "visualStyle"):
                if key not in frame:
                    errors.append(f"frames[{index}] missing {key}")
    return errors


def check_media_manifest(reference_manifest: dict[str, Any], media_manifest: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    assets = reference_manifest.get("assets") if isinstance(reference_manifest.get("assets"), list) else []
    files = media_manifest.get("files") if isinstance(media_manifest.get("files"), list) else []
    if len(assets) != len(files):
        errors.append(f"media_manifest file count {len(files)} does not match reference asset count {len(assets)}")
    asset_ids = {str(asset.get("assetId") or "") for asset in assets}
    media_asset_ids = {
        str((item.get("metadata") if isinstance(item.get("metadata"), dict) else {}).get("assetId") or "")
        for item in files
    }
    missing = sorted(asset_ids - media_asset_ids)
    extra = sorted(media_asset_ids - asset_ids)
    if missing:
        errors.append(f"media_manifest is missing asset ids: {missing}")
    if extra:
        errors.append(f"media_manifest has unknown asset ids: {extra}")
    for asset in assets:
        media_id = str(asset.get("mediaId") or "")
        matching = [item for item in files if item.get("id") == media_id]
        if len(matching) != 1:
            errors.append(f"asset {asset.get('assetId')} mediaId {media_id} has {len(matching)} media_manifest matches")
    return errors


def select_contact_frames(analysis: dict[str, Any]) -> list[dict[str, Any]]:
    frames = analysis.get("frames") if isinstance(analysis.get("frames"), list) else []
    if not frames:
        return []
    if len(frames) <= 3:
        return frames
    return [frames[0], frames[len(frames) // 2], frames[-1]]


def build_contact_sheet(items: list[dict[str, str]], output: Path) -> None:
    if not items:
        return
    thumb_width = 360
    thumb_height = 220
    caption_height = 34
    columns = 2
    rows = (len(items) + columns - 1) // columns
    sheet = Image.new("RGB", (columns * thumb_width, rows * (thumb_height + caption_height)), "white")
    draw = ImageDraw.Draw(sheet)
    for index, item in enumerate(items):
        path = Path(item["path"])
        if not path.exists():
            continue
        image = Image.open(path).convert("RGB")
        image.thumbnail((thumb_width, thumb_height))
        x = (index % columns) * thumb_width
        y = (index // columns) * (thumb_height + caption_height)
        sheet.paste(image, (x + (thumb_width - image.width) // 2, y))
        caption = item["caption"][:58]
        draw.rectangle([x, y + thumb_height, x + thumb_width, y + thumb_height + caption_height], fill="#111827")
        draw.text((x + 8, y + thumb_height + 9), caption, fill="white")
    output.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(output, quality=92)


def validate_asset(asset: dict[str, Any], schema: dict[str, Any], *, verify_hashes: bool) -> tuple[dict[str, Any], list[dict[str, str]]]:
    errors: list[dict[str, str]] = []
    warnings: list[dict[str, str]] = []
    asset_id = str(asset.get("assetId") or "")
    for key in ("sourcePath", "originalPath", "analysisPath"):
        value = str(asset.get(key) or "")
        if not value or not Path(value).exists():
            errors.append({"assetId": asset_id, "field": key, "message": f"path does not exist: {value}"})
    if verify_hashes:
        expected = str(asset.get("sha256") or "")
        for key in ("sourcePath", "originalPath"):
            path = Path(str(asset.get(key) or ""))
            if path.exists() and expected and sha256_file(path) != expected:
                errors.append({"assetId": asset_id, "field": key, "message": "sha256 mismatch"})
    analysis_payload: dict[str, Any] | None = None
    analysis_path = Path(str(asset.get("analysisPath") or ""))
    if analysis_path.exists():
        try:
            analysis_payload = load_json(analysis_path)
        except (OSError, json.JSONDecodeError) as error:
            errors.append({"assetId": asset_id, "field": "analysisPath", "message": f"invalid JSON: {error}"})
        if analysis_payload is not None:
            for message in validate_with_schema(analysis_payload, schema):
                errors.append({"assetId": asset_id, "field": "analysis", "message": message})
            analysis_asset = analysis_payload.get("asset") if isinstance(analysis_payload.get("asset"), dict) else {}
            if str(analysis_asset.get("assetId") or "") != asset_id:
                errors.append({"assetId": asset_id, "field": "analysis.asset.assetId", "message": "assetId mismatch"})
            for frame in analysis_payload.get("frames", []) if isinstance(analysis_payload.get("frames"), list) else []:
                for frame_path_key in ("samplePath", "debugOverlayPath"):
                    frame_path = str(frame.get(frame_path_key) or "")
                    if frame_path and not Path(frame_path).exists():
                        errors.append({"assetId": asset_id, "field": frame_path_key, "message": f"path does not exist: {frame_path}"})
            if not analysis_payload.get("summary", {}).get("facePresent") and analysis_payload.get("summary", {}).get("personPresent"):
                warnings.append({"assetId": asset_id, "field": "summary", "message": "person detected without face detection"})
    return {
        "assetId": asset_id,
        "collection": asset.get("collection"),
        "kind": asset.get("kind"),
        "sourcePath": asset.get("sourcePath"),
        "analysisPath": asset.get("analysisPath"),
        "ok": not errors,
        "errorCount": len(errors),
        "warningCount": len(warnings),
    }, errors + warnings


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate reference asset manifest and per-asset analysis JSON.")
    parser.add_argument("--manifest", type=Path, default=MANIFEST_PATH)
    parser.add_argument("--media-manifest", type=Path, default=MEDIA_MANIFEST_PATH)
    parser.add_argument("--schema", type=Path, default=SCHEMA_PATH)
    parser.add_argument("--qa-report", type=Path, default=QA_REPORT_PATH)
    parser.add_argument("--contact-sheet", type=Path, default=CONTACT_SHEET_PATH)
    parser.add_argument("--no-hash", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    reference_manifest = load_json(args.manifest)
    media_manifest = load_json(args.media_manifest)
    schema = load_json(args.schema)
    assets = reference_manifest.get("assets") if isinstance(reference_manifest.get("assets"), list) else []
    errors: list[dict[str, str]] = []
    warnings: list[dict[str, str]] = []
    asset_reports: list[dict[str, Any]] = []
    contact_items: list[dict[str, str]] = []

    for message in check_media_manifest(reference_manifest, media_manifest):
        errors.append({"assetId": "", "field": "media_manifest", "message": message})

    for asset in assets:
        report, findings = validate_asset(asset, schema, verify_hashes=not args.no_hash)
        asset_reports.append(report)
        for item in findings:
            if item["message"].startswith("person detected without"):
                warnings.append(item)
            else:
                errors.append(item)
        analysis_path = Path(str(asset.get("analysisPath") or ""))
        if analysis_path.exists():
            try:
                analysis = load_json(analysis_path)
                for frame in select_contact_frames(analysis):
                    debug_path = str(frame.get("debugOverlayPath") or "")
                    if debug_path:
                        contact_items.append(
                            {
                                "path": debug_path,
                                "caption": f"{asset.get('assetId')} {frame.get('frameId')} t={frame.get('timeSeconds')}",
                            }
                        )
            except (OSError, json.JSONDecodeError):
                pass

    build_contact_sheet(contact_items, args.contact_sheet)
    payload = {
        "schemaVersion": "reference-assets-qa/v1",
        "generatedAt": utc_now(),
        "ok": not errors,
        "assetCount": len(assets),
        "mediaManifestCount": len(media_manifest.get("files", [])) if isinstance(media_manifest.get("files"), list) else 0,
        "analysisCount": sum(1 for asset in assets if Path(str(asset.get("analysisPath") or "")).exists()),
        "contactSheetPath": str(args.contact_sheet) if args.contact_sheet.exists() else "",
        "errors": errors,
        "warnings": warnings,
        "assets": asset_reports,
    }
    write_json(args.qa_report, payload)
    print(json.dumps({"ok": payload["ok"], "errors": len(errors), "warnings": len(warnings), "qaReport": str(args.qa_report)}, ensure_ascii=False, indent=2))
    if errors:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
