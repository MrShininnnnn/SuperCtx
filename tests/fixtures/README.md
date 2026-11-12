# Released shim fixtures

`released_shims.json` contains the UTF-8 strings returned by the **released**
`superctx.shim.generate_shim` implementations:

- v0.1.4: `f51d395878148c2134391aa5090ce282702c0aff`
- v0.2.5: `34c6d4f9f88beb64f4bb0a48f625a759ebda7282`

Each tag's `scripts/superctx` directory was extracted using `git archive` into
a unique temporary directory. A separate `python -I` process imported that
extracted package, then rendered `AGENTS.md` with `plain-pointer` and
`.claude/CLAUDE.md` with `claude-at-import`, for both `backup_required` values.
The JSON records those returned strings verbatim. The working-tree renderer
was not imported. Keep these historical fixtures fixed when changing rendering.
