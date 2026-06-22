"""
ObsidianService — read/write/search the Obsidian vault at ~/Obsidian/coding/.
Parses markdown frontmatter, [[wikilinks]], and builds a simple knowledge graph.
"""

import os
import re
from collections import defaultdict
from datetime import date, datetime, timezone, timedelta
from pathlib import Path
from typing import Optional

TZ = timezone(timedelta(hours=8))
VAULT_ROOT = Path.home() / "Obsidian" / "coding"

YAML_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)
WIKILINK_RE = re.compile(r"\[\[([^\]|#]+)(?:[|#][^\]]+)?\]\]")


class ObsidianService:
    """Singleton service for Obsidian vault operations."""

    def __init__(self, vault_path: Path = VAULT_ROOT):
        self.vault = vault_path

    def list_files(self, subdir: str = "") -> list[dict]:
        base = self.vault / subdir if subdir else self.vault
        if not base.exists():
            return []
        items = []
        for entry in sorted(base.iterdir()):
            if entry.name.startswith("."):
                continue
            if entry.is_dir():
                items.append({"name": entry.name, "type": "directory",
                    "path": str(entry.relative_to(self.vault)),
                    "children_count": len([f for f in entry.iterdir() if f.suffix == ".md"])})
            elif entry.suffix == ".md":
                try: stat = entry.stat()
                except Exception: continue
                items.append({"name": entry.name, "type": "file",
                    "path": str(entry.relative_to(self.vault)),
                    "size": stat.st_size,
                    "modified": datetime.fromtimestamp(stat.st_mtime, tz=TZ).isoformat()})
        return items

    def tree(self) -> dict:
        def _walk(p: Path) -> dict:
            node = {"name": p.name, "type": "directory", "children": []}
            try:
                for e in sorted(p.iterdir()):
                    if e.name.startswith("."): continue
                    if e.is_dir():
                        c = _walk(e)
                        if c["children"]: node["children"].append(c)
                    elif e.suffix == ".md":
                        node["children"].append({"name": e.name, "type": "file",
                            "path": str(e.relative_to(self.vault))})
            except PermissionError: pass
            return node
        root = _walk(self.vault)
        root["name"] = "coding"
        return root

    def read_note(self, rel_path: str) -> Optional[dict]:
        full = self.vault / rel_path
        if not full.exists() or not full.is_file(): return None
        try: content = full.read_text(encoding="utf-8")
        except Exception: return None
        fm = self._parse_frontmatter(content)
        links = list(set(WIKILINK_RE.findall(content)))
        return {"path": rel_path, "name": full.name, "content": content,
            "frontmatter": fm, "links": links,
            "size": full.stat().st_size,
            "modified": datetime.fromtimestamp(full.stat().st_mtime, tz=TZ).isoformat()}

    def write_note(self, rel_path: str, content: str) -> dict:
        full = self.vault / rel_path
        full.parent.mkdir(parents=True, exist_ok=True)
        full.write_text(content, encoding="utf-8")
        return {"path": rel_path, "status": "saved"}

    def search(self, query: str, limit: int = 20) -> list[dict]:
        results = []
        ql = query.lower()
        for root, dirs, files in os.walk(self.vault):
            dirs[:] = [d for d in dirs if not d.startswith(".")]
            for fn in files:
                if not fn.endswith(".md"): continue
                fp = Path(root) / fn
                try: content = fp.read_text(encoding="utf-8")
                except Exception: continue
                idx = content.lower().find(ql)
                if idx < 0: continue
                s = max(0, idx - 40); e = min(len(content), idx + len(query) + 80)
                snippet = content[s:e].replace("\n", " ").strip()
                if s > 0: snippet = "..." + snippet
                if e < len(content): snippet += "..."
                results.append({"path": str(fp.relative_to(self.vault)), "name": fn,
                    "snippet": snippet, "score": content.lower().count(ql)})
        results.sort(key=lambda r: -r["score"])
        return results[:limit]

    def build_graph(self) -> dict:
        nodes, edges, pid = [], [], {}
        # Nodes
        for root, dirs, files in os.walk(self.vault):
            dirs[:] = [d for d in dirs if not d.startswith(".")]
            for fn in files:
                if not fn.endswith(".md"): continue
                fp = Path(root) / fn
                rel = str(fp.relative_to(self.vault))
                pid[rel] = len(nodes)
                g = rel.split("/")[0] if "/" in rel else "root"
                try: fl = fp.read_text(encoding="utf-8")[:200]
                except Exception: fl = ""
                tm = re.search(r"^#\s+(.+)", fl, re.MULTILINE)
                title = tm.group(1).strip() if tm else fn.replace(".md", "")
                try: sz = fp.stat().st_size
                except Exception: sz = 1000
                nodes.append({"id": pid[rel], "path": rel, "label": title[:40],
                    "group": g, "size": max(8, min(24, sz // 500))})
        # Edges
        edge_labels = defaultdict(set)
        for rel in pid:
            try: content = (self.vault / rel).read_text(encoding="utf-8")
            except Exception: continue
            for link in WIKILINK_RE.findall(content):
                resolved = self._resolve_wikilink(link, rel)
                if resolved and resolved in pid and resolved != rel:
                    key = (min(pid[rel], pid[resolved]), max(pid[rel], pid[resolved]))
                    edge_labels[key].add(link)
        for (s, t), labels in edge_labels.items():
            edges.append({"source": s, "target": t, "label": ", ".join(list(labels)[:2])})
        groups = defaultdict(int)
        for n in nodes: groups[n["group"]] += 1
        return {"nodes": nodes, "edges": edges, "stats": {"total_nodes": len(nodes), "total_edges": len(edges), "groups": dict(groups)}}

    def _resolve_wikilink(self, link: str, from_path: str) -> Optional[str]:
        cands = [link + ".md", link]
        d = os.path.dirname(from_path)
        if d: cands += [os.path.join(d, link + ".md"), os.path.join(d, link)]
        for c in cands:
            if (self.vault / c).exists(): return c
        ll = link.lower().replace(" ", "")
        for root, dirs, files in os.walk(self.vault):
            dirs[:] = [d for d in dirs if not d.startswith(".")]
            for f in files:
                if f.lower().replace(" ", "").startswith(ll):
                    return str((Path(root) / f).relative_to(self.vault))
        return None

    def get_stats(self) -> dict:
        tn = tw = tc = 0
        groups = defaultdict(lambda: {"notes": 0, "words": 0})
        for root, dirs, files in os.walk(self.vault):
            dirs[:] = [d for d in dirs if not d.startswith(".")]
            for fn in files:
                if not fn.endswith(".md"): continue
                tn += 1
                try: content = (Path(root) / fn).read_text(encoding="utf-8")
                except Exception: continue
                w = len(re.findall(r"\w+", content))
                tw += w; tc += len(content)
                g = str(Path(root).relative_to(self.vault)) if self.vault != Path(root) else "root"
                groups[g]["notes"] += 1; groups[g]["words"] += w
        return {"total_notes": tn, "total_words": tw, "total_chars": tc, "by_folder": dict(sorted(groups.items()))}

    def get_backlinks(self, rel_path: str) -> list[dict]:
        # Match either strict lowercase equality OR a whitespace-stripped
        # comparison — wikilinks like [[ReAct 模式]] should still resolve to
        # the file `ReAct模式.md`. Same fuzzy rule `_resolve_wikilink` uses
        # to build the graph, so backlinks stay consistent with it.
        target = os.path.splitext(os.path.basename(rel_path))[0].lower()
        target_compact = target.replace(" ", "").replace("　", "")
        results = []
        for root, dirs, files in os.walk(self.vault):
            dirs[:] = [d for d in dirs if not d.startswith(".")]
            for fn in files:
                if not fn.endswith(".md"): continue
                fp = Path(root) / fn; rel = str(fp.relative_to(self.vault))
                if rel == rel_path: continue
                try: content = fp.read_text(encoding="utf-8")
                except Exception: continue
                for link in WIKILINK_RE.findall(content):
                    lk = link.lower()
                    if lk == target or lk.replace(" ", "").replace("　", "") == target_compact:
                        results.append({"path": rel, "name": fn, "link_text": link}); break
        return results

    def get_daily_note(self, day: str | None = None) -> Optional[dict]:
        if day is None: day = date.today().isoformat()
        rel = f"daily/{day}.md"
        n = self.read_note(rel)
        if n: return n
        self.write_note(rel, f"---\ndate: {day}\ntags: [daily]\n---\n\n# {day}\n\n")
        return self.read_note(rel)

    def _parse_frontmatter(self, content: str) -> dict:
        m = YAML_RE.match(content)
        if not m: return {}
        try:
            fm = {}
            for line in m.group(1).strip().split("\n"):
                if ":" in line:
                    k, _, v = line.partition(":"); k = k.strip(); v = v.strip().strip('"').strip("'")
                    if v.startswith("[") and v.endswith("]"): v = [x.strip().strip('"').strip("'") for x in v[1:-1].split(",")]
                    fm[k] = v
            return fm
        except Exception: return {}

obsidian = ObsidianService()
