# Experiment report

Every step of the original lab README, plus the pipeline experiments built on top of it, run on 2026-11-15 with DVC 3.67.1 and Python 3.13.9 on macOS. Each section links to its full, unedited terminal log in [docs/logs/](docs/logs/). Only absolute paths in the logs were shortened.

**Contents**

1. [Project initialization](#1-project-initialization)
2. [GCS remote](#2-gcs-remote)
3. [Tracking dataset v1](#3-tracking-dataset-v1)
4. [Dataset change → new hash (v2)](#4-dataset-change--new-hash-v2)
5. [Reverting to a previous version](#5-reverting-to-a-previous-version)
6. [Pipeline](#6-pipeline)
7. [Catching a misleading metric](#7-catching-a-misleading-metric)
8. [Experiment sweep (17 runs)](#8-experiment-sweep-17-runs)
9. [Comparing, promoting and sharing](#9-comparing-promoting-and-sharing)
10. [Collaborator workflow: clone, pull, fetch](#10-collaborator-workflow-clone-pull-fetch)
11. [Garbage collection](#11-garbage-collection)
12. [Move, remove, unprotect, list, diff, destroy](#12-move-remove-unprotect-list-diff-destroy)
13. [Lessons learned](#13-lessons-learned)

---

## 1. Project initialization
Log: [01_init.log](docs/logs/01_init.log)

`git init` and `dvc init`, which creates `.dvc/config`, `.dvc/.gitignore` and `.dvcignore`. The raw CSV is deliberately **not** added to git; DVC owns it.

## 2. GCS remote
Logs: [02_gcs.log](docs/logs/02_gcs.log), [03_remote.log](docs/logs/03_remote.log)

- Created bucket `gs://dvc-lab1-cc-segmentation-shivam` in **us-east1** (README step 5), with uniform bucket-level access and public access prevention enforced.
- `dvc remote add -d gcsremote gs://dvc-lab1-cc-segmentation-shivam`.
- **Authentication:** the README's service-account key (steps 7–10) was **not** created during this run. DVC authenticated through gcloud Application Default Credentials, which `dvc-gs` picks up automatically. [scripts/setup_gcs_service_account.sh](scripts/setup_gcs_service_account.sh) does the README's service-account steps from the CLI, with least-privilege `roles/storage.objectAdmin` on the bucket instead of project *Owner*. It stores the key path with `dvc remote modify --local`, so it lands in the git-ignored `.dvc/config.local` and is never committed. Use it for CI or any machine without your login.

## 3. Tracking dataset v1
Log: [04_track_v1.log](docs/logs/04_track_v1.log)

```
dvc add data/CC_GENERAL.csv            -> md5 9f38ecac…, 893,928 bytes
git add data/CC_GENERAL.csv.dvc data/.gitignore && git commit && git tag data-v1
dvc push                               -> 1 file pushed
gcloud storage ls -r gs://…            -> files/md5/9f/38ecac62d17b286b138db019dd2616
```

`dvc status -c` goes from `new: data/CC_GENERAL.csv` to `Cache and remote 'gcsremote' are in sync.`

## 4. Dataset change → new hash (v2)
Logs: [05_data_v2.log](docs/logs/05_data_v2.log), [05a_data_v2_first_attempt.log](docs/logs/05a_data_v2_first_attempt.log)

The `validate` stage found real problems in the raw export:

| Issue | Rows |
|---|---|
| `MINIMUM_PAYMENTS` null | 313 (left for imputation) |
| `CREDIT_LIMIT` null | 1 |
| `CASH_ADVANCE_FREQUENCY` > 1 (impossible for a ratio) | 8 |

**v2 ("cleaned release")** drops the 9 invalid rows: 8,950 → 8,941 rows. Running `dvc add` again produced a new hash, `f9eb4259…` (893,035 bytes). `git diff` on the `.dvc` file shows exactly the md5 and size change. After `dvc push`, both versions sit in the bucket as separate objects.

> **First attempt (kept as a lesson):** the first v2 script round-tripped the CSV through pandas. That reformatted every number (`1000` → `1000.0`), so the file *grew* to 1,010,331 bytes even though rows were removed. DVC is content-addressed, so any byte change gives a new hash. The script was rewritten to drop lines textually, keeping every surviving row byte-identical. The orphaned object from that attempt was later removed with `dvc gc --cloud` (§ 11).

## 5. Reverting to a previous version
Log: [06_revert.log](docs/logs/06_revert.log)

Both methods restore v1 byte for byte:

| Method | Commands | Result |
|---|---|---|
| README method: whole commit | `git checkout 30df547` → `dvc checkout` | 8,950 rows, md5 `9f38ecac…` |
| Single file: keep current code | `git checkout data-v1 -- data/CC_GENERAL.csv.dvc` → `dvc checkout data/CC_GENERAL.csv.dvc` | 8,950 rows, md5 `9f38ecac…` |
| Back to latest | `git checkout main` (or `HEAD -- <file>.dvc`) → `dvc checkout` | 8,941 rows, md5 `f9eb4259…` |

## 6. Pipeline
Log: [07_pipeline.log](docs/logs/07_pipeline.log)

Five stages added with `dvc stage add` (`-d` deps, `-p` param sections, `-o` cached outputs, `-O` git-tracked outputs, `-M` metrics), then the top-level `plots:` block was written into `dvc.yaml`. `dvc dag` and `dvc dag --mermaid` show the graph.

- First `dvc repro`: all 5 stages, about 10 s.
- Second `dvc repro`: every stage `didn't change, skipping`.
- `dvc push`: 5 outputs uploaded (features, scaler, model, assignments, PCA plot).

Baseline (tag `baseline`, K-Means k=4): silhouette **0.2173**, Davies-Bouldin 1.687, Calinski-Harabasz 2,267. The elbow knee from `kneed` is **k=6**.

## 7. Catching a misleading metric
Logs: [09_exp_sweeps.log](docs/logs/09_exp_sweeps.log), [10_eval_fix.log](docs/logs/10_eval_fix.log)

The first experiment sweep ranked **min-max scaling** best by a wide margin (silhouette 0.279 vs 0.217). But silhouette was being computed in each experiment's *own* feature space. Changing the scaler changes the geometry the metric is measured in, so those numbers aren't on the same scale. Re-scoring the same labels in one fixed reference space told a different story:

| Scaler | Own-space silhouette | Reference-space silhouette |
|---|---|---|
| standard (baseline) | 0.2173 | 0.2173 |
| min-max | 0.2788 | **0.2079** |
| robust | 0.2587 | **0.1951** |
| no log transform | 0.1951 | **0.1138** |

**Fix:** `evaluate` now also reports `silhouette_ref`, `davies_bouldin_ref` and `calinski_harabasz_ref`, computed in a fixed space defined in `params.yaml → evaluate.reference`. `dvc status` showed only `evaluate` was stale, so `dvc repro` re-ran just that stage. `dvc params diff` and `dvc metrics diff` showed the new keys. The stale pre-fix runs were later removed with `dvc exp remove --rev baseline`.

## 8. Experiment sweep (17 runs)
Logs: [08_exp_data.log](docs/logs/08_exp_data.log), [11_exp_rerun.log](docs/logs/11_exp_rerun.log)

All runs were queued with `dvc exp run --queue` and executed by `dvc queue start -j 4`. The four unnamed rows came from one grid command: `-S 'train.algorithm=gmm,agglomerative' -S 'train.n_clusters=5,6'`. `raw-data-v1` was queued with the v1 `.dvc` pointer checked out, so the experiment captures a **data version**, not just parameters. All 17 succeeded.

Sorted by `silhouette_ref` (higher is better). DB = Davies-Bouldin (lower is better).

| Experiment | Change from baseline | k | Silhouette (own) | **Silhouette (ref)** | DB (ref) | Smallest segment |
|---|---|---|---|---|---|---|
| k3 | `n_clusters=3` | 3 | 0.2251 | **0.2251** | 1.680 | 32.0% |
| k5 | `n_clusters=5` | 5 | 0.2193 | **0.2193** | 1.600 | 15.5% |
| **k-auto** ✅ | `n_clusters=auto` (knee → 6) | 6 | 0.2182 | **0.2182** | **1.465** | 11.3% |
| k6 | `n_clusters=6` | 6 | 0.2182 | 0.2182 | 1.465 | 11.3% |
| *baseline* | – | 4 | 0.2173 | 0.2173 | 1.687 | 17.6% |
| no-clip | `clip_quantile=1.0` | 4 | 0.2166 | 0.2172 | 1.688 | 17.6% |
| mean-impute | `impute_strategy=mean` | 4 | 0.2156 | 0.2161 | 1.688 | 18.2% |
| k8 | `n_clusters=8` | 8 | 0.2153 | 0.2153 | 1.435 | 5.3% |
| raw-data-v1 | dataset **v1** (uncleaned) | 4 | 0.2136 | 0.2136 | 1.660 | 16.7% |
| minmax-scaler | `scaler=minmax` | 4 | *0.2788* | 0.2079 | 1.764 | 22.6% |
| robust-scaler | `scaler=robust` | 4 | *0.2587* | 0.1951 | 1.731 | 13.3% |
| gmm-k4 | `algorithm=gmm` | 4 | 0.1771 | 0.1771 | 1.893 | 18.2% |
| agglo-k4 | `algorithm=agglomerative` | 4 | 0.1737 | 0.1737 | 1.709 | 14.2% |
| tense-drop | gmm, k=6 | 6 | 0.1728 | 0.1728 | 2.335 | 6.4% |
| burly-mate | agglomerative, k=5 | 5 | 0.1697 | 0.1697 | 1.874 | 12.2% |
| muzzy-tics | gmm, k=5 | 5 | 0.1612 | 0.1612 | 2.464 | 7.1% |
| rowdy-peri | agglomerative, k=6 | 6 | 0.1562 | 0.1562 | 1.689 | 12.2% |
| no-log | `log_transform=false` | 4 | 0.1951 | 0.1138 | 1.866 | 7.9% |

The full table with every column is in [docs/experiments.csv](docs/experiments.csv), exported with `dvc exp show --csv`.

**Findings**

- **Algorithm:** K-Means beats GMM and Ward agglomerative at every k tried.
- **Log transform:** this matters most. Without `log1p` the skewed dollar columns dominate and quality collapses (0.114).
- **Clipping and imputation:** winsorizing and median vs mean imputation make almost no difference (±0.001).
- **Data cleaning (v1 vs v2):** a small but real improvement. 9 bad rows out of 8,950 moved silhouette 0.2136 → 0.2173 and stopped one cluster swelling to 35% of customers.
- **Choice of k:** silhouette is flat across K-Means k=3…8 (0.215–0.225), so it doesn't settle the choice on its own.

**Selection rule:** among K-Means runs whose smallest segment holds at least 10% of customers (so every segment is actionable), take the best Davies-Bouldin, with reference silhouette no worse than baseline. **k-auto** (= k6) wins: DB 1.465 vs 1.600 (k5) and 1.687 (baseline). It is also the elbow knee, and `auto` re-derives k if the data changes. k3 has the top silhouette but only three segments, too coarse for marketing. k8 has the best DB but leaves a 5% segment.

## 9. Comparing, promoting and sharing
Logs: [12_compare.log](docs/logs/12_compare.log), [13_promote.log](docs/logs/13_promote.log), [14_share.log](docs/logs/14_share.log)

- `dvc exp diff main k-auto` and `dvc exp diff k-auto minmax-scaler --param-deps` show metric and param deltas.
- `dvc plots diff main k-auto minmax-scaler -o docs/plots_compare` renders a side-by-side HTML report: elbow curve, silhouette vs k, cluster sizes, PCA scatter, PCA image.
- `dvc exp apply k-auto`, then commit and tag `model-v1`, then `dvc push` (3 new objects).
- Git server: a local bare repository stood in for GitHub (`origin`). Nothing was pushed to GitHub.
  - `git push origin main --tags`.
  - `dvc exp push origin k-auto minmax-scaler raw-data-v1` pushed the experiment refs to git and their 10 artifacts to GCS.
  - `dvc exp list origin --all-commits` lists the three.

## 10. Collaborator workflow: clone, pull, fetch
Logs: [15_collaborator.log](docs/logs/15_collaborator.log), [16_fetch_checkout.log](docs/logs/16_fetch_checkout.log)

In a fresh `git clone`, the data starts out missing (`dvc status`: `deleted: data/CC_GENERAL.csv`).

- **`dvc pull`:** 6 files fetched from GCS. The dataset md5 matches (`f9eb4259…`), `dvc metrics show` matches, and `dvc repro` has **nothing to recompute**. That is full reproducibility.
- **`dvc exp pull origin minmax-scaler`:** brings a teammate's experiment into the clone.
- **`dvc fetch` vs `checkout`:** after deleting the cache and the data file, `dvc fetch data/CC_GENERAL.csv.dvc` downloads only into `.dvc/cache` (the workspace stays empty). `dvc checkout` then links it into the workspace.

## 11. Garbage collection
Log: [17_gc.log](docs/logs/17_gc.log)

| Command | Effect |
|---|---|
| `dvc gc --workspace --dry` | would delete 65 of 71 cached objects, including **dataset v1**. Workspace-only GC is dangerous when old versions still matter. |
| `dvc gc --all-tags --all-branches --all-experiments -f` | removed 3 truly unreferenced objects (71 → 68) |
| `dvc gc --cloud … --dry`, then the real run | removed exactly **1** object from GCS: the orphan from the failed v2 attempt (21 → 20). v1 (`9f/38ec…`) and v2 (`f9/eb42…`) were verified still present. |

## 12. Move, remove, unprotect, list, diff, destroy
Logs: [18_move.log](docs/logs/18_move.log), [19_remove_unprotect.log](docs/logs/19_remove_unprotect.log), [20_debug.log](docs/logs/20_debug.log), [21_destroy.log](docs/logs/21_destroy.log)

- **`dvc move data/CC_GENERAL.csv data/raw/CC_GENERAL.csv`** rewrote the `.dvc` file and `.gitignore` entries; the pipeline paths were updated to match. `dvc repro` re-ran validate, preprocess and evaluate, which read the moved path. `features.csv` came out byte-identical, so **elbow and train were skipped**. No metric changed.
- **`dvc remove`:** tracked a 100-row sample, then stopped tracking it. Its `.gitignore` entry was removed and the file stayed on disk.
- **`dvc unprotect` / `dvc cache dir`:** the cache is in `.dvc/cache`. On APFS, DVC uses reflinks, so workspace files are already writable and `unprotect` is effectively a no-op.
- **`dvc version`** (same output as `dvc doctor`), and **`dvc list`** on:
  - this repo, with `-R --dvc-only`;
  - an old revision, `--rev data-v1`;
  - the bare git server;
  - the upstream course repo on GitHub, which shows its only DVC-tracked file is `data/data.txt`.
- **`dvc diff data-v1 model-v1`**, **`dvc metrics diff baseline model-v1`**, **`dvc params diff baseline model-v1`**.
- **`dvc config --list --show-origin`**.
- **`dvc destroy -f`**, run in the throwaway collaborator clone, never this repo. It removed `.dvc/`, `dvc.yaml`, `dvc.lock`, `.dvcignore` and every `.dvc` file, and left the data files behind as plain, untracked files.

## 13. Lessons learned

1. **Metrics are only comparable within one feature space.** Without the `*_ref` metrics, this sweep would have promoted a worse model.
2. **Hashes are byte-level.** A "harmless" re-save through pandas created a whole new 1 MB version. Write data-cleaning scripts so unchanged rows stay byte-identical.
3. **`dvc gc -w` deletes old dataset versions.** Use `--all-tags --all-experiments` (and `--dry` first), especially with `--cloud`.
4. **Experiments can version data, not just params.** Queuing with an older `.dvc` pointer checked out gives a reproducible data-version comparison.
5. **Keep credentials out of `.dvc/config`.** Use ADC or `dvc remote modify --local`. The upstream repo committed an absolute key path.
