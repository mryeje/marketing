# Insert / replace the SERVER-SIDE NORMALIZATION block with this debug-enhanced variant.
# Place this where the prior "SERVER-SIDE NORMALIZATION: run recipe_normalizer" logic lives.

# SERVER-SIDE NORMALIZATION + DEBUG DUMP: run recipe_normalizer (if available) before validation
if _HAS_NORMALIZER:
    try:
        wrapped = normalize_recipe(wrapped)
        print("[INFO] Recipe normalized by recipe_normalizer")
        # Debug dump: write normalized payload to a temp file for inspection by user
        try:
            norm_tmp = tempfile.NamedTemporaryFile(mode="w", suffix=".normalized.json", delete=False, encoding="utf-8")
            json.dump(wrapped, norm_tmp, ensure_ascii=False, indent=2)
            norm_tmp.flush()
            norm_tmp_path = norm_tmp.name
            norm_tmp.close()
            print(f"[DEBUG] Wrote normalized recipe to: {norm_tmp_path}")
            # Log clip summary (count + ids + first clip preview)
            try:
                recipe_obj = wrapped.get("recipe", wrapped) if isinstance(wrapped, dict) else wrapped
                clips = recipe_obj.get("clips", []) if isinstance(recipe_obj, dict) else []
                print(f"[DEBUG] Normalized recipe clips count: {len(clips)}")
                if isinstance(clips, list) and clips:
                    ids = [c.get("id", f"<no-id-{i}>") for i, c in enumerate(clips, start=1)]
                    print(f"[DEBUG] Normalized recipe clip ids: {ids}")
                    # print a trimmed preview of the first clip
                    import copy
                    first_clip = copy.deepcopy(clips[0])
                    # redact large fields if any
                    print("[DEBUG] First clip preview:", json.dumps(first_clip, ensure_ascii=False, indent=2)[:2000])
            except Exception as e:
                print("[WARN] Unable to extract clip summary from normalized recipe:", e)
        except Exception as e:
            print("[WARN] Could not write normalized recipe to temp file:", e)
    except Exception as ex:
        print("[ERROR] recipe_normalizer failed:", ex)
        traceback.print_exc()
        # Return a clear 400 so clients see the normalization error
        raise HTTPException(status_code=400, detail={"status": "error", "message": "recipe normalization failed", "detail": str(ex)})
else:
    print("[WARN] recipe_normalizer not present; skipping normalization. Recommend adding recipe_normalizer.py to server directory.")