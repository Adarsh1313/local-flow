# Fast local file search on Windows 11 (for a v2 "find report.pdf" voice command)

Researched 2026-10-31. Goal: offline, free, low idle CPU/RAM, callable from Python 3.12 on a Ryzen 5 3550H.
No decision is made here. Items marked (unverified) came from general knowledge or snippets, not a source I read.
Stars/dates are from the GitHub API on the research date.

## Comparison

| Option | First index / query speed | Admin? | Idle CPU / RAM | Licence | Install burden | Python path | Maintenance |
|---|---|---|---|---|---|---|---|
| Everything 1.4 + es.exe / SDK | ~5 s per 250k files, ~1 min per 1M; queries in ms | Needs admin OR the Everything service for NTFS | ~35 MB per 250k files, ~100 MB per 1M | Freeware, closed source | Install Everything (+ optional es.exe, winget) | `subprocess` es.exe, or ctypes on Everything64.dll | Active (voidtools) |
| Everything 1.5 alpha (SDK3, named pipes) | Same engine | Same | Same | Freeware, closed | Alpha build, separate instance name | python-everything (SDK3 wrapper) | Alpha, active |
| Windows Search (SystemIndex) | Already indexed by OS; query ~ms-100s of ms (unverified) | No | 0 extra if the OS indexer is already running | OS component | None | win32com ADODB or pyodbc-style OLE DB | Microsoft, legacy API but stable |
| MFT/USN reader, own build (ntfs-reader, mft) | Full MFT scan, seconds (ntfs-reader README: ~12 s uncached, ~4 s cached; hardware unstated) | Yes (raw volume) | Whatever you build | Apache-2.0 | Rust toolchain + PyO3 or a helper exe | Write a binding yourself | ntfs-reader active, solo author |
| goz (Rust, MFT + USN daemon) | Beats Everything in its own benchmark (7800X3D) | Daemon elevated; client not | ~12 MB resident idle (3.97M entries, author figure) | MIT | Download 2 exes, install service | `subprocess goz --json` or named pipe | Brand new, 21 stars |
| WizFile | MFT scan, "fraction of a second" searches | Not stated | Not stated | Free personal use, closed | Installer/portable (unverified) | None found (GUI only) | Active (antibody-software) |
| Indexer++ | MFT-based, no timings found | Probably (unverified) | Not stated | MIT | Build/binary from repo | `ifind` CLI via subprocess | Stalled (last release 2018) |
| fd (live walk) | No index; full C: walk is seconds to minutes (no source measured) | No | 0 idle (no daemon) | Apache-2.0 | One exe (winget/scoop) | `subprocess fd` | Very active, 44.9k stars |
| ripgrep `--files` | Same as fd; no index | No | 0 idle | Unlicense | One exe | `subprocess rg --files` | Very active, 69.6k stars |
| Python `os.scandir` walk | Slowest; no index | No | 0 idle | PSF | None | Native | n/a |

## Per-option notes

### Everything (voidtools)
- Indexes names only, via MFT; keeps current via the USN journal, including changes made while closed ([FAQ](https://www.voidtools.com/faq/)).
- NTFS needs admin or the Everything service; installing the service avoids repeated UAC prompts.
- es.exe requires Everything to be installed and running; use `-n`, `-json`, `-instance`, `-timeout` ([CLI docs](https://www.voidtools.com/support/everything/command_line_interface/)). A forum report says the "IPC window not found" error needs `-instance 1.5a` for 1.5 ([forum](https://www.voidtools.com/forum/viewtopic.php?p=76252)). Sources conflict on whether the service alone (no GUI) is enough.
- Idle cost is a resident process (RAM scales with file count). goz's benchmark measured Everything at 369 MB resident on a 3.97M-entry index.
- Python: official SDK is a DLL over IPC ([SDK](https://www.voidtools.com/en-us/support/everything/sdk/)); a ctypes example is on the forum ([example](https://voidtools.com/forum/viewtopic.php?p=29598)). [Spavid04/python-everything](https://github.com/Spavid04/python-everything): 7 stars, no licence shown, thin ctypes-style wrapper, no pip package, last push 2025-08.
- Offline and free, but closed source and a second always-running app the user must install.

### Windows Search index (SystemIndex)
- Zero install and no admin: query via OLE DB provider `Search.CollatorDSO`, table `SYSTEMINDEX`, read-only SQL ([MS docs](https://learn.microsoft.com/en-us/windows/win32/search/using-sql-and-aqs-to-query-the-index)).
- From Python: `win32com.client.Dispatch("ADODB.Connection")` is the likely route (unverified, no Python source found). Needs pywin32.
- Weaknesses: only indexed locations (users' folders by default, unverified), results depend on indexer state, and the user may have disabled the service.
- Reuses an indexer that is already running, so no extra idle cost. Likely the lowest-burden fallback.

### MFT / USN readers
- [kikijiki/ntfs-reader](https://github.com/kikijiki/ntfs-reader) (Rust): 22 stars, Apache-2.0, pushed 2026-10-24, author not accepting PRs ([docs.rs](https://docs.rs/crate/ntfs-reader/latest)). Needs elevation; no Python bindings.
- [omerbenamram/mft](https://github.com/omerbenamram/mft): 161 stars, Apache-2.0, active. Parses MFT files for forensics, not a live volume reader or search engine.
- [ColinFinck/ntfs](https://github.com/ColinFinck/ntfs): 603 stars, Apache-2.0, last push 2026-01.
- Python-only: [PoorBillionaire/USN-Journal-Parser](https://github.com/PoorBillionaire/USN-Journal-Parser) (119 stars, last push 2022) parses USN dumps, not a search index.
- Building your own means owning a persistent index, USN tailing and an elevated helper. Largest effort.

### goz
- [mustafaahci/goz](https://github.com/mustafaahci/goz): MIT, 21 stars, pushed 2026-10-10. Daemon (`gozd.exe`, elevated, can be a Windows service) plus unelevated client with `--json` and es.exe-style flags.
- Benchmarks ([BENCHMARKS.md](https://github.com/mustafaahci/goz/blob/main/docs/BENCHMARKS.md)): `.pdf` query 14.5 ms vs Everything 39.5 ms over a pipe; 12 MB idle RAM vs 369 MB. Author's own numbers on a faster CPU; not independently verified.
- Very young project and a single maintainer. NTFS only.

### WizFile and other closed tools
- [WizFile](https://antibody-software.com/wizfile/) reads the MFT directly; free for personal use; no CLI/API mentioned, so hard to automate.
- UltraSearch, Listary, Agent Ransack are proprietary ([AlternativeTo](https://alternativeto.net/software/wizfile/)).
- "Orange Search": no results found.
- [Indexer++](https://github.com/dfs-minded/indexer-plus-plus): MIT, reads the MFT, has `ifind` CLI; development stalled since ~2018 ([AlternativeTo](https://alternativeto.net/software/indexer-/about)).

### fd / ripgrep walkers
- [sharkdp/fd](https://github.com/sharkdp/fd) and [BurntSushi/ripgrep](https://github.com/BurntSushi/ripgrep) walk the directory tree live (parallel), no admin, no daemon, zero idle.
- No Windows full-drive benchmark found. ripgrep's Windows performance is a known open question ([issue 555](https://www.github.com/BurntSushi/ripgrep/issues/555)). A cold C: walk is plausibly slow on a 3550H with a laptop disk; measure with `Measure-Command { fd -H -I . C:\ }` (suggested, not run).
- Good for scoped queries ("find report.pdf in Documents"); poor for whole-drive queries.

### Other notable repos
- [Flow-Launcher/Flow.Launcher](https://github.com/Flow-Launcher/Flow.Launcher): MIT, 15.9k stars; uses Everything as a plugin, evidence the Everything integration pattern is common.
- [elis132/everything-mcp](https://github.com/elis132/everything-mcp): MIT, 30 stars, wraps es.exe; shows a working es.exe wrapper approach.
- [Chaoses-Ib/ib-everything](https://github.com/Chaoses-Ib/ib-everything): MIT, 20 stars, Rust/C++ port of the Everything IPC SDK.

## Likely shortlist for v2 (no decision)
1. Everything + es.exe via `subprocess` (`-n 10 -json`). Fastest proven path; costs a resident app and admin/service setup.
2. Windows Search SystemIndex via pywin32. No new install, no admin; limited to indexed locations.
3. fd scoped to user folders as a no-dependency fallback. Zero idle cost; slower on whole-drive queries.
4. Watch goz: best idle RAM, but new and single-maintainer.

Open questions to settle before choosing: measured idle CPU/RAM on the 3550H, whether the user accepts installing a third-party app, and whether results must cover all drives or only user folders.

## Sources
- https://www.voidtools.com/faq/
- https://www.voidtools.com/support/everything/command_line_interface/
- https://www.voidtools.com/en-us/support/everything/sdk/
- https://www.voidtools.com/forum/viewtopic.php?p=76252
- https://voidtools.com/forum/viewtopic.php?p=29598
- https://github.com/Spavid04/python-everything
- https://learn.microsoft.com/en-us/windows/win32/search/using-sql-and-aqs-to-query-the-index
- https://docs.rs/crate/ntfs-reader/latest
- https://github.com/kikijiki/ntfs-reader
- https://github.com/omerbenamram/mft
- https://github.com/ColinFinck/ntfs
- https://github.com/mustafaahci/goz
- https://github.com/mustafaahci/goz/blob/main/docs/BENCHMARKS.md
- https://antibody-software.com/wizfile/
- https://alternativeto.net/software/wizfile/
- https://alternativeto.net/software/indexer-/about
- https://github.com/dfs-minded/indexer-plus-plus
- https://github.com/sharkdp/fd
- https://github.com/BurntSushi/ripgrep
- https://www.github.com/BurntSushi/ripgrep/issues/555
- https://github.com/Flow-Launcher/Flow.Launcher
- https://github.com/elis132/everything-mcp
- https://github.com/Chaoses-Ib/ib-everything
- https://github.com/PoorBillionaire/USN-Journal-Parser
