# Working on Chameleon

- Branch from `main`: `feat/<short-name>` or `fix/<short-name>`. Open a pull request; CI must be green before merging.
- Run tests before pushing: `python -m unittest discover -s tests -v`.
- Keep the engine deterministic: same input → same output. AI may recognise roles/subjects, never place pixels.
- Every new engine stage gets unit tests; every UI drag gets a click or keyboard alternative.
- Never commit `data/`, `.env` files, API keys or large binaries. Test designs go in `examples/`.
- Track work against [docs/PLAN.md](docs/PLAN.md); tick boxes in the same PR that finishes them.
