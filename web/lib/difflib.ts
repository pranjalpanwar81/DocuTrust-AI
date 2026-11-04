// Faithful port of the parts of Python's difflib used by DocuTrust:
// SequenceMatcher.ratio / quick_ratio / real_quick_ratio and get_close_matches.
// Kept identical so typo correction behaves exactly like the original backend.

class SequenceMatcher {
  private a = "";
  private b = "";
  private b2j = new Map<string, number[]>();
  private fullbcount: Map<string, number> | null = null;
  private matchingBlocks: Array<[number, number, number]> | null = null;

  setSeq1(a: string) {
    this.a = a;
    this.matchingBlocks = null;
  }

  setSeq2(b: string) {
    this.b = b;
    this.matchingBlocks = null;
    this.fullbcount = null;
    this.b2j = new Map();
    for (let i = 0; i < b.length; i++) {
      const ch = b[i];
      const list = this.b2j.get(ch);
      if (list) list.push(i);
      else this.b2j.set(ch, [i]);
    }
    // Python's autojunk only applies when len(b) >= 200; query words never are.
    if (b.length >= 200) {
      const ntest = Math.floor(b.length / 100) + 1;
      for (const [ch, idxs] of [...this.b2j]) {
        if (idxs.length > ntest) this.b2j.delete(ch);
      }
    }
  }

  private findLongestMatch(alo: number, ahi: number, blo: number, bhi: number): [number, number, number] {
    const { a, b, b2j } = this;
    let besti = alo, bestj = blo, bestsize = 0;
    let j2len = new Map<number, number>();
    for (let i = alo; i < ahi; i++) {
      const newj2len = new Map<number, number>();
      const js = b2j.get(a[i]) ?? [];
      for (const j of js) {
        if (j < blo) continue;
        if (j >= bhi) break;
        const k = (j2len.get(j - 1) ?? 0) + 1;
        newj2len.set(j, k);
        if (k > bestsize) {
          besti = i - k + 1;
          bestj = j - k + 1;
          bestsize = k;
        }
      }
      j2len = newj2len;
    }
    while (besti > alo && bestj > blo && a[besti - 1] === b[bestj - 1]) {
      besti--; bestj--; bestsize++;
    }
    while (besti + bestsize < ahi && bestj + bestsize < bhi && a[besti + bestsize] === b[bestj + bestsize]) {
      bestsize++;
    }
    return [besti, bestj, bestsize];
  }

  private getMatchingBlocks(): Array<[number, number, number]> {
    if (this.matchingBlocks) return this.matchingBlocks;
    const la = this.a.length, lb = this.b.length;
    const queue: Array<[number, number, number, number]> = [[0, la, 0, lb]];
    const blocks: Array<[number, number, number]> = [];
    while (queue.length) {
      const [alo, ahi, blo, bhi] = queue.pop()!;
      const x = this.findLongestMatch(alo, ahi, blo, bhi);
      const [i, j, k] = x;
      if (k) {
        blocks.push(x);
        if (alo < i && blo < j) queue.push([alo, i, blo, j]);
        if (i + k < ahi && j + k < bhi) queue.push([i + k, ahi, j + k, bhi]);
      }
    }
    blocks.sort((p, q) => p[0] - q[0] || p[1] - q[1] || p[2] - q[2]);
    this.matchingBlocks = blocks;
    return blocks;
  }

  ratio(): number {
    const matches = this.getMatchingBlocks().reduce((sum, block) => sum + block[2], 0);
    return calculateRatio(matches, this.a.length + this.b.length);
  }

  quickRatio(): number {
    if (!this.fullbcount) {
      this.fullbcount = new Map();
      for (const ch of this.b) this.fullbcount.set(ch, (this.fullbcount.get(ch) ?? 0) + 1);
    }
    const avail = new Map<string, number>();
    let matches = 0;
    for (const ch of this.a) {
      const numb = avail.has(ch) ? avail.get(ch)! : (this.fullbcount.get(ch) ?? 0);
      avail.set(ch, numb - 1);
      if (numb > 0) matches++;
    }
    return calculateRatio(matches, this.a.length + this.b.length);
  }

  realQuickRatio(): number {
    const la = this.a.length, lb = this.b.length;
    return calculateRatio(Math.min(la, lb), la + lb);
  }
}

function calculateRatio(matches: number, length: number): number {
  return length ? (2.0 * matches) / length : 1.0;
}

/** Python difflib.get_close_matches(word, possibilities, n, cutoff). */
export function getCloseMatches(word: string, possibilities: Iterable<string>, n = 3, cutoff = 0.6): string[] {
  const result: Array<[number, string]> = [];
  const s = new SequenceMatcher();
  s.setSeq2(word);
  for (const x of possibilities) {
    s.setSeq1(x);
    if (s.realQuickRatio() >= cutoff && s.quickRatio() >= cutoff && s.ratio() >= cutoff) {
      result.push([s.ratio(), x]);
    }
  }
  // heapq.nlargest compares (score, word) tuples: higher score first, then larger string.
  result.sort((p, q) => (q[0] - p[0]) || (q[1] > p[1] ? 1 : q[1] < p[1] ? -1 : 0));
  return result.slice(0, n).map(([, x]) => x);
}
