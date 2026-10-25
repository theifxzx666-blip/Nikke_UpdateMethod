#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""国服 Addressables catalog 解析：把 m_*DataString 解成条目表。

格式依据实测（small_0930.json，527 个 key）：
  m_KeyDataString : int32 count，随后 count 个 object
                    object = byte type + payload
                      type 0 ASCII   : int32 len + bytes
                      type 1 Unicode : int32 len + utf-16-le bytes
                      type 2 UInt16  : 2
                      type 3 UInt32  : 4
                      type 4 Int32   : 4
                      type 5 Hash128 : 16
  m_BucketDataString : int32 bucketCount，随后每个 bucket =
                       int32 keyIndex + int32 entryCount + entryCount*int32
  m_EntryDataString  : entryCount 条 × 7 个 int32
                       (internalId, provider, dependencyKey, depHash,
                        dataIndex, primaryKey, resourceType)
"""
import base64
import json
import struct
import sys
from pathlib import Path


def read_objects(raw: bytes):
    """返回 [(记录起始 offset, 值)]。

    bucket 里存的不是对象索引，而是**该 key 在 KeyData 里的字节偏移**
    （指向 type 字节）。实测 small_0930：bucket0=4 正好是第 0 个 key 的记录起点。
    """
    off = 0
    (count,) = struct.unpack_from("<i", raw, off)
    off += 4
    out = []
    for _ in range(count):
        start = off
        t = raw[off]
        off += 1
        if t == 0:
            (n,) = struct.unpack_from("<i", raw, off)
            off += 4
            out.append((start, raw[off:off + n].decode("ascii", "replace")))
            off += n
        elif t == 1:
            (n,) = struct.unpack_from("<i", raw, off)
            off += 4
            out.append((start, raw[off:off + n * 2].decode("utf-16-le", "replace")))
            off += n * 2
        elif t == 2:
            out.append((start, struct.unpack_from("<H", raw, off)[0]))
            off += 2
        elif t == 3:
            out.append((start, struct.unpack_from("<I", raw, off)[0]))
            off += 4
        elif t == 4:
            out.append((start, struct.unpack_from("<i", raw, off)[0]))
            off += 4
        elif t == 5:
            out.append((start, raw[off:off + 16].hex()))
            off += 16
        else:
            raise ValueError(f"未知 type={t} @ {off - 1}")
    if off != len(raw):
        raise ValueError(f"读完剩 {len(raw) - off} 字节，解析不完整")
    return out


def read_buckets(raw: bytes, key_offsets: set, entry_count: int):
    off = 0
    (n,) = struct.unpack_from("<i", raw, off)
    off += 4
    buckets = []
    for _ in range(n):
        key_off, ent_n = struct.unpack_from("<ii", raw, off)
        off += 8
        ents = list(struct.unpack_from(f"<{ent_n}i", raw, off))
        off += 4 * ent_n
        buckets.append((key_off, ents))
    if off != len(raw):
        raise ValueError(f"bucket 读完剩 {len(raw) - off} 字节")
    for k, ents in buckets:
        if k not in key_offsets:
            raise ValueError(f"keyOff {k} 不是任何 key 的记录起点")
        for e in ents:
            if not (0 <= e < entry_count):
                raise ValueError(f"entry 索引 {e} 越界（共 {entry_count} 条）")
    return buckets


def read_entries(raw: bytes):
    """int32 count，随后 count 条 × 7 个 int32（28 字节）。"""
    (n,) = struct.unpack_from("<i", raw, 0)
    body = raw[4:]
    if len(body) != n * 28:
        raise ValueError(f"entry count={n} 但正文 {len(body)} 字节（应为 {n * 28}）")
    return [struct.unpack_from("<7i", body, i * 28) for i in range(n)]


def parse(path: Path):
    d = json.loads(path.read_text(encoding="utf-8"))
    kpairs = read_objects(base64.b64decode(d["m_KeyDataString"]))
    entries = read_entries(base64.b64decode(d["m_EntryDataString"]))
    buckets = read_buckets(base64.b64decode(d["m_BucketDataString"]),
                           {o for o, _ in kpairs}, len(entries))
    keys = [v for _, v in kpairs]
    key_by_off = dict(kpairs)
    internal_ids = d["m_InternalIds"]
    for e in entries:
        if not (0 <= e[0] < len(internal_ids)):
            raise ValueError(f"internalId 索引 {e[0]} 越界")
    return {
        "locator": d["m_LocatorId"],
        "span": d.get("m_ProjSpan", ""),
        "keys": keys,
        "key_by_off": key_by_off,
        "buckets": buckets,
        "entries": entries,
        "internal_ids": internal_ids,
        "provider_ids": d["m_ProviderIds"],
        "raw": d,
    }


def bundle_name(internal_id: str) -> str:
    """去掉 {HostKey}/ 前缀，**保留资源内部的子路径**。

    不能写成 rsplit("/", 1)[-1]：大厅动画的 id 形如
      {Host}/spinestandingcharactergroup(hd)_assets_spine/standing/c010/00_hd_<md5>.bundle
    取末段会把 `spine/standing/c010` 全丢掉，所有角色塌缩成同一个 `00_hd`，
    diff 时互相覆盖 → 整批大厅"无变化"（E-40）。
    """
    if internal_id.startswith("{"):
        i = internal_id.find("}")
        if i > 0:
            return internal_id[i + 1:].lstrip("/")
    return internal_id


def bundle_hash(name: str) -> str:
    """xxx_<32hex>.bundle → 32hex；不是这形状就返回空。"""
    if not name.endswith(".bundle"):
        return ""
    parts = name[:-7].rsplit("_", 1)
    if len(parts) == 2 and len(parts[1]) == 32 and all(c in "0123456789abcdef" for c in parts[1]):
        return parts[1]
    return ""


if __name__ == "__main__":
    p = Path(sys.argv[1])
    r = parse(p)
    print(f"locator   : {r['locator']}")
    print(f"ProjSpan  : {r['span']}")
    print(f"keys      : {len(r['keys'])}")
    print(f"buckets   : {len(r['buckets'])}")
    print(f"entries   : {len(r['entries'])}")
    print(f"internalIds: {len(r['internal_ids'])}")
    nb = sum(1 for x in r["internal_ids"] if x.endswith(".bundle"))
    nh = sum(1 for x in r["internal_ids"] if bundle_hash(bundle_name(x)))
    print(f"  其中 .bundle {nb} 个，带 32 位 hash {nh} 个")
    print("--- keys 前 3 ---")
    for k in r["keys"][:3]:
        print("  ", k)
    print("--- 非字符串 key ---")
    odd = [k for k in r["keys"] if not isinstance(k, str)]
    print("  ", len(odd), odd[:5])
