# Freshness verification architecture

## Decision

PIE keeps content hashes as the authority. A filesystem journal may be used as
an acceleration hint, never as proof. If the journal is unavailable, truncated,
overrun, or cannot prove the complete project interval, PIE falls back to a full
inventory/hash scan and fails closed on partial discovery.

The durable design is a content-addressed manifest:

1. Read every eligible file and compute its SHA-256 while building a manifest.
2. Store the ordered `(relative_path, sha256, size)` set and a manifest digest.
3. Persist the journal cursor/volume identity only as an invalidation hint.
4. On a later query, consume journal events since the cursor; any uncertainty
   invalidates the hint and triggers a full scan.
5. Re-read and hash files used in published evidence; never trust cached bytes
   from an earlier inventory as the current source.

NTFS USN records are persistent but can be deleted and only describe that a
change occurred, not the resulting content; therefore they cannot replace
hash verification. Linux inotify events can overflow, are not recursive, and
rename pairing is inherently racy, so the same fallback rule is required.

The first safe optimization remains local: avoid duplicate directory traversal
within one explicitly scoped verification object, while retaining a final
current-file hash before publication. Persistent reuse should be introduced only
with journal coverage proofs and tests for content-preserving timestamp changes,
create/delete, rename, journal loss, and queue overflow.

The first measured discovery optimization filters non-Python files before
per-file symlink and ignore-rule checks. Directory filtering is unchanged, and
Python files still receive the same ignore and hash validation. On the Doctor
Mesh snapshot this reduced median verification from roughly 0.21--0.36 s to
0.07--0.08 s without changing the manifest or freshness contract.
