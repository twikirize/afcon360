# Ask Mode — AFCON360

When answering questions about this codebase:
- Always frame answers in the context of Flask/SQLAlchemy/PostgreSQL
- Reference the module structure when relevant (events, wallet, identity, etc.)
- If a question touches wallet logic, note the double-entry ledger constraint
- If a question involves IDs, clarify: `user.id` (BigInteger, internal) vs `user.public_id` (UUID, external)
- PowerShell context: any shell commands must be Windows/PowerShell compatible

---

# Debug Mode — AFCON360

## Common Error Patterns in This Project

### SQLAlchemy startup crash
- Check for duplicate `backref` names across related models
- Check for circular imports (identity ↔ feature modules)
- Check `BaseModel` inheritance — `db.Model` direct use will cause issues

### Alembic migration failure
- "type already exists" → ENUM type conflict → switch to String column in model
- "table already exists" → migration ran partially before → use `sa.inspect()` existence checks
- "Can't locate revision" → alembic_version table mismatch → run `flask db stamp head`

### Template/AJAX errors
- 404 on pane load → check `?_pane=1` conditional in base.html
- Dropdown does nothing → check for `overflow: hidden` on parent, or inline `onclick` being escaped by Jinja2 `|e`
- CSRF error → verify `{{ csrf_token() }}` not `{{ csrf_token }}`

### Docker/deployment issues
- Container won't start → check CRLF line endings in `docker-entrypoint.sh`
- Redis connection error → verify `RATELIMIT_STORAGE_URI` key name
- Fernet error on startup → check for module-level instantiation, use lazy `_get_fernet()`

## Debug Report Format
1. **Root cause:** one clear sentence
2. **Evidence:** which file/line/log message points to it
3. **Fix:** exact change needed
4. **Verify:** how to confirm it's resolved
