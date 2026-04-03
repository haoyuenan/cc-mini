# Code Review Report: Commit `b349a6b` - "fix skill addition"

## Summary

This commit modified `src/core/skills.py` to add type coercion for skill metadata fields. The change introduces a helper function `_ensure_str()` and applies it to string fields in `_skill_from_frontmatter()`.

---

## Changes Identified

### Added: `_ensure_str()` helper function (lines 112-118)
```python
def _ensure_str(val: Any, default: str = "") -> str:
    """Coerce *val* to a string — rejoin lists produced by the frontmatter parser."""
    if val is None:
        return default
    if isinstance(val, list):
        return ", ".join(str(v) for v in val)
    return str(val)
```

### Modified: `_skill_from_frontmatter()` function (lines 121-147)

**Before:**
```python
return Skill(
    name=meta.get("name", name),
    description=meta.get("description", ""),
    when_to_use=meta.get("when_to_use", ""),
    ...
    context=meta.get("context", "inline"),
    argument_hint=meta.get("arguments", ""),
    ...
)
```

**After:**
```python
return Skill(
    name=_ensure_str(meta.get("name"), name),
    description=_ensure_str(meta.get("description")),
    when_to_use=_ensure_str(meta.get("when_to_use")),
    ...
    context=_ensure_str(meta.get("context"), "inline"),
    argument_hint=_ensure_str(meta.get("arguments")),
    ...
)
```

---

## Findings

### **Warning** — Type coercion may mask underlying parsing issues

**Location:** `_ensure_str()` function and its usage

**Issue:** The `_ensure_str()` function converts `None` to a default value and joins lists with `", "`. While this prevents crashes, it may hide issues in the frontmatter parser (`_parse_frontmatter`):

1. **List handling inconsistency**: The frontmatter parser (lines 100-101) already handles comma-separated lists:
   ```python
   elif "," in val:
       meta[key] = [v.strip() for v in val.split(",") if v.strip()]
   ```
   If a field like `description` or `name` contains a comma, it becomes a list. `_ensure_str()` then rejoins it, potentially changing the original value.

2. **Example scenario**: A skill with `description: "Hello, world!"` would be parsed as a list `["Hello", "world!"]`, then converted back to `"Hello, world!"` — but this loses the original quoting intent.

**How to apply:** Consider whether the frontmatter parser should distinguish between quoted strings containing commas vs. actual comma-separated lists, or document that commas in string fields should be avoided.

---

### **Suggestion** — Missing `_ensure_str` on `model` field

**Location:** Line 140 in `_skill_from_frontmatter()`

```python
model=meta.get("model"),
```

**Issue:** The `model` field is passed directly without type coercion. While `model` expects `str | None`, if the frontmatter parser incorrectly produces a list, it would not be handled.

**How to apply:** For consistency, consider:
```python
model=_ensure_str(meta.get("model")) or None,
```
Or document that `model` is intentionally excluded since it should always be a single string or `None`.

---

### **Suggestion** — Consider logging or warning on type coercion

**Location:** `_ensure_str()` function

**Issue:** When `_ensure_str()` converts a list to a string or `None` to a default, it happens silently. Users might be unaware their frontmatter is being interpreted differently than expected.

**How to apply:** Consider adding a warning log when type coercion occurs:
```python
if isinstance(val, list):
    import warnings
    warnings.warn(f"List value coerced to string: {val}")
    return ", ".join(str(v) for v in val)
```

---

## Positive Observations

✅ **Fixes a real bug**: The change addresses a legitimate issue where `meta.get()` could return types incompatible with the `Skill` dataclass fields.

✅ **Backward compatible**: The change adds safety without breaking existing functionality.

✅ **Minimal scope**: The fix is targeted and doesn't introduce unnecessary complexity.

✅ **Good docstring**: The `_ensure_str()` function has a clear docstring explaining its purpose.

---

## Summary Table

| Severity | Count | Description |
|----------|-------|-------------|
| Critical | 0 | — |
| Warning | 1 | Type coercion may mask parsing issues |
| Suggestion | 2 | Missing `_ensure_str` on `model`; consider logging |

---

## Conclusion

This is a reasonable defensive fix that prevents type errors when frontmatter metadata doesn't match expected types. The main concern is that the fix works around potential issues in the frontmatter parser rather than addressing them at the source. Consider reviewing `_parse_frontmatter()` to ensure quoted strings with commas are handled correctly.

---

## Fix Applied (2026-04-03)

### Problem
The frontmatter parser checked for commas **before** checking for quoted strings, causing values like `"Hello, world!"` to be incorrectly parsed as a list `["Hello", "world!"]`.

### Solution
Reordered the parsing logic in `_parse_frontmatter()` to check for quoted strings **before** checking for commas:

```python
# Before (incorrect order):
# 1. Boolean
# 2. List (comma-separated)  ← checked first
# 3. Quoted string           ← checked after

# After (correct order):
# 1. Boolean
# 2. Quoted string           ← checked first
# 3. List (comma-separated)  ← checked after
```

### Tests Added
- `test_quoted_values_with_commas`: Verifies that quoted strings containing commas are preserved as strings
- `test_unquoted_comma_becomes_list`: Verifies that unquoted comma-separated values still become lists