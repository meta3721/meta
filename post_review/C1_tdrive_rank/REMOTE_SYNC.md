# Copy laptop tree → 4090 (run in a *local* terminal; you will type the SSH password)

Remote: `root@117.50.171.236` port **23** (Cursor SSH / AutoDL-style).

From **Git Bash on the laptop** (not the remote bash):

```bash
HOST=root@117.50.171.236
PORT=23
SRC=/c/Cursor/raven.mcs
DST=/root/raven.mcs

ssh -p $PORT $HOST 'mkdir -p /root/raven.mcs'
# code + frozen experiment (skip .venv, unrelated artifacts)
rsync -avP -e "ssh -p $PORT" \
  --exclude '.venv*' --exclude '__pycache__' --exclude '.git' \
  "$SRC/src/" "$HOST:$DST/src/"
rsync -avP -e "ssh -p $PORT" \
  "$SRC/scripts/run_tdrive_rank_v1.py" \
  "$SRC/scripts/compute_tdrive_phi.py" \
  "$HOST:$DST/scripts/"
rsync -avP -e "ssh -p $PORT" \
  "$SRC/post_review/C1_tdrive_rank/" "$HOST:$DST/post_review/C1_tdrive_rank/"
rsync -avP -e "ssh -p $PORT" \
  "$SRC/data/processed/tdrive_speed/" "$HOST:$DST/data/processed/tdrive_speed/"
rsync -avP -e "ssh -p $PORT" \
  "$SRC/artifacts/e3_tdrive_rank_eventtraces_v1/" \
  "$HOST:$DST/artifacts/e3_tdrive_rank_eventtraces_v1/"
rsync -avP -e "ssh -p $PORT" \
  "$SRC/results_tdrive_rank/round_v1/" "$HOST:$DST/results_tdrive_rank/round_v1/"
rsync -avP -e "ssh -p $PORT" \
  "$SRC/tdrive_protocol_seal_r1/" "$HOST:$DST/tdrive_protocol_seal_r1/"
```

If `rsync` is missing locally, use `scp -P 23 -r`. Processed+traces are ~570 MB.

Then in the **4090 Cursor window**: File → Open Folder → `/root/raven.mcs` → new Agent chat → paste `REMOTE_AGENT_PROMPT.md`.
