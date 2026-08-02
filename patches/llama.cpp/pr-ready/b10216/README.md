# Local b10216 mail series

This directory contains the exact three-patch llama.cpp source diff validated by
E6d/E6e, expressed as a reviewable `git format-patch` series against tag
`b10216`, commit `876a4321163249c43ca4e986818fab5ab081f282`.

The patches are deliberately separate commits with focused messages and
`Signed-off-by` trailers. The cover letter records why they are grouped and the
existing native Arm evidence. No upstream pull request or mail submission has
been opened.

Apply the series to the exact base with:

```bash
git checkout --detach 876a4321163249c43ca4e986818fab5ab081f282
git am --3way \
  /path/to/Arm/patches/llama.cpp/pr-ready/b10216/000[1-3]-*.patch
```

The resulting full-index source diff must have SHA-256
`e11cdd41091d5d76b973c67ffcc04429760fbef58c7a2bc971947b80900a9893`,
identical to [`../../b10216/e6f-current-series.patch`](../../b10216/e6f-current-series.patch).
The cover letter is not passed to `git am`.

E9d freezes and runs the unpublished series through native GCC, native Clang,
and a targeted Clang ASan+UBSan lane. Those results are evidence about this
exact local series; they do not imply broader upstream CI or maintainer review.
