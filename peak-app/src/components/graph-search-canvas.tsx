"use client";

import { useEffect, useRef } from "react";
import { useTheme } from "next-themes";
import { cn } from "@/lib/utils";

/**
 * A slowly rotating 3D graph on which a shortest-path search runs over and
 * over: BFS, Dijkstra and A* take turns finding a route between two random
 * nodes, lighting up the frontier and visited nodes as they go, then tracing
 * the path they found.
 *
 * Drawn on a plain 2D canvas with a small perspective projection, so it
 * needs no 3D library. It pauses while off screen and shows a still frame
 * when the visitor prefers reduced motion.
 */

type Variant = "hero" | "subtle";
type Algorithm = "BFS" | "Dijkstra" | "A*";
type Phase = "search" | "trace" | "hold" | "fade";

type Vec3 = { x: number; y: number; z: number };
type Edge = { a: number; b: number; w: number };
type Link = { to: number; edge: number; w: number };

type Palette = {
  edge: string;
  edgeAlpha: number;
  node: string;
  nodeAlpha: number;
  explored: string;
  exploredAlpha: number;
  frontier: string;
  path: string;
  pathAlpha: number;
  packet: string;
  source: string;
  target: string;
  label: string;
  glow: boolean;
};

// Black and ash tones, with a few accents so the search stays readable:
// green start, rose target, amber frontier.
const PALETTES: Record<"hero" | "subtleLight" | "subtleDark", Palette> = {
  hero: {
    edge: "168,162,158",
    edgeAlpha: 0.16,
    node: "214,211,209",
    nodeAlpha: 0.5,
    explored: "231,229,228",
    exploredAlpha: 0.45,
    frontier: "251,191,36",
    path: "255,255,255",
    pathAlpha: 1,
    packet: "255,255,255",
    source: "52,211,153",
    target: "251,113,133",
    label: "214,211,209",
    glow: true,
  },
  subtleLight: {
    edge: "41,37,36",
    edgeAlpha: 0.1,
    node: "41,37,36",
    nodeAlpha: 0.22,
    explored: "28,25,23",
    exploredAlpha: 0.2,
    frontier: "217,119,6",
    path: "12,10,9",
    pathAlpha: 0.55,
    packet: "12,10,9",
    source: "5,150,105",
    target: "225,29,72",
    label: "87,83,78",
    glow: false,
  },
  subtleDark: {
    edge: "214,211,209",
    edgeAlpha: 0.08,
    node: "214,211,209",
    nodeAlpha: 0.2,
    explored: "231,229,228",
    exploredAlpha: 0.18,
    frontier: "251,191,36",
    path: "245,245,244",
    pathAlpha: 0.5,
    packet: "255,255,255",
    source: "52,211,153",
    target: "251,113,133",
    label: "168,162,158",
    glow: false,
  },
};

const ALGORITHMS: Algorithm[] = ["Dijkstra", "BFS", "A*"];
const NEIGHBOURS = 3;
const CAMERA_DISTANCE = 3.4;
const HOLD_MS = 2600;
const FADE_MS = 900;

// --------------------------------------------------------------------------
// Graph construction
// --------------------------------------------------------------------------

function distance(p: Vec3, q: Vec3): number {
  return Math.hypot(p.x - q.x, p.y - q.y, p.z - q.z);
}

/** Points spread through a sphere, kept apart so the graph reads clearly. */
function scatterPoints(count: number): Vec3[] {
  const points: Vec3[] = [];
  const minGap = 1.1 / Math.cbrt(count);
  let attempts = 0;
  while (points.length < count && attempts < count * 200) {
    attempts++;
    const p = {
      x: Math.random() * 2 - 1,
      y: Math.random() * 2 - 1,
      z: Math.random() * 2 - 1,
    };
    if (p.x * p.x + p.y * p.y + p.z * p.z > 1) continue;
    if (points.every((q) => distance(p, q) >= minGap)) points.push(p);
  }
  return points;
}

/** Links each node to its nearest neighbours, then joins any islands. */
function buildGraph(points: Vec3[]) {
  const n = points.length;
  const edges: Edge[] = [];
  const seen = new Set<string>();
  const addEdge = (a: number, b: number) => {
    const key = a < b ? `${a}-${b}` : `${b}-${a}`;
    if (a === b || seen.has(key)) return;
    seen.add(key);
    edges.push({ a, b, w: distance(points[a], points[b]) });
  };

  for (let i = 0; i < n; i++) {
    const nearest = points
      .map((p, j) => ({ j, d: distance(points[i], p) }))
      .filter(({ j }) => j !== i)
      .sort((p, q) => p.d - q.d)
      .slice(0, NEIGHBOURS);
    for (const { j } of nearest) addEdge(i, j);
  }

  // Union-find: keep joining the closest pair of nodes across two components
  // until the whole graph is connected, so every search can succeed.
  const parent = Array.from({ length: n }, (_, i) => i);
  const find = (i: number): number =>
    parent[i] === i ? i : (parent[i] = find(parent[i]));
  for (const { a, b } of edges) parent[find(a)] = find(b);

  for (;;) {
    const root = find(0);
    let best: { a: number; b: number; d: number } | null = null;
    for (let a = 0; a < n; a++) {
      if (find(a) !== root) continue;
      for (let b = 0; b < n; b++) {
        if (find(b) === root) continue;
        const d = distance(points[a], points[b]);
        if (!best || d < best.d) best = { a, b, d };
      }
    }
    if (!best) break;
    addEdge(best.a, best.b);
    parent[find(best.b)] = root;
  }

  const links: Link[][] = Array.from({ length: n }, () => []);
  edges.forEach(({ a, b, w }, edge) => {
    links[a].push({ to: b, edge, w });
    links[b].push({ to: a, edge, w });
  });
  return { edges, links };
}

// --------------------------------------------------------------------------
// One run of a search algorithm, advanced one node at a time
// --------------------------------------------------------------------------

class Search {
  readonly cost: Float64Array;
  readonly via: Int32Array; // edge used to reach each node, -1 if none
  readonly nodeState: Uint8Array; // 0 unseen, 1 frontier, 2 visited
  readonly edgeLitAt: Float64Array; // when the edge was explored, -1 if not
  readonly open: number[] = [];
  readonly order: number[] = []; // FIFO queue for BFS
  path: number[] = []; // edge ids from source to target
  pathNodes: number[] = [];
  visited = 0;
  done = false;

  constructor(
    readonly algorithm: Algorithm,
    readonly source: number,
    readonly target: number,
    private readonly points: Vec3[],
    private readonly links: Link[][],
    edgeCount: number,
  ) {
    const n = points.length;
    this.cost = new Float64Array(n).fill(Infinity);
    this.via = new Int32Array(n).fill(-1);
    this.nodeState = new Uint8Array(n);
    this.edgeLitAt = new Float64Array(edgeCount).fill(-1);
    this.cost[source] = 0;
    this.nodeState[source] = 1;
    this.open.push(source);
  }

  private priority(node: number): number {
    if (this.algorithm === "A*") {
      return (
        this.cost[node] + distance(this.points[node], this.points[this.target])
      );
    }
    return this.cost[node];
  }

  private popNext(): number | undefined {
    if (this.algorithm === "BFS") return this.open.shift();
    let best = 0;
    for (let i = 1; i < this.open.length; i++) {
      if (this.priority(this.open[i]) < this.priority(this.open[best]))
        best = i;
    }
    return this.open.splice(best, 1)[0];
  }

  /** Visits one node. Returns false once the search is over. */
  step(now: number): boolean {
    if (this.done) return false;
    let node = this.popNext();
    while (node !== undefined && this.nodeState[node] === 2) {
      node = this.popNext();
    }
    if (node === undefined) {
      this.done = true;
      return false;
    }

    this.nodeState[node] = 2;
    this.visited++;
    if (node === this.target) {
      this.tracePath();
      this.done = true;
      return false;
    }

    for (const { to, edge, w } of this.links[node]) {
      if (this.nodeState[to] === 2) continue;
      const next = this.cost[node] + (this.algorithm === "BFS" ? 1 : w);
      if (next < this.cost[to]) {
        this.cost[to] = next;
        this.via[to] = edge;
        if (this.edgeLitAt[edge] < 0) this.edgeLitAt[edge] = now;
        if (this.nodeState[to] === 0 || this.algorithm !== "BFS") {
          this.open.push(to);
        }
        this.nodeState[to] = 1;
      }
    }
    return true;
  }

  private tracePath() {
    const edges: number[] = [];
    const nodes: number[] = [this.target];
    let node = this.target;
    while (node !== this.source) {
      const edge = this.via[node];
      edges.push(edge);
      node = this.links[node].find((l) => l.edge === edge)!.to;
      nodes.push(node);
    }
    this.path = edges.reverse();
    this.pathNodes = nodes.reverse();
  }

  /** Real length of the path found, whatever the algorithm counted. */
  pathLength(): number {
    let total = 0;
    for (let i = 1; i < this.pathNodes.length; i++) {
      total += distance(
        this.points[this.pathNodes[i - 1]],
        this.points[this.pathNodes[i]],
      );
    }
    return total;
  }
}

/** A source and a far-away target, so each search has some work to do. */
function pickEndpoints(links: Link[][]): [number, number] {
  const n = links.length;
  const source = Math.floor(Math.random() * n);
  const hops = new Array<number>(n).fill(-1);
  hops[source] = 0;
  const queue = [source];
  for (let i = 0; i < queue.length; i++) {
    for (const { to } of links[queue[i]]) {
      if (hops[to] < 0) {
        hops[to] = hops[queue[i]] + 1;
        queue.push(to);
      }
    }
  }
  const furthest = Math.max(...hops);
  const far = hops
    .map((h, i) => ({ h, i }))
    .filter(({ h }) => h >= Math.max(2, Math.floor(furthest * 0.75)));
  const target =
    far[Math.floor(Math.random() * far.length)]?.i ?? queue.at(-1)!;
  return [source, target];
}

// --------------------------------------------------------------------------
// Component
// --------------------------------------------------------------------------

type GraphSearchCanvasProps = {
  variant?: Variant;
  /** Shows the algorithm name and its progress in the corner. */
  showLabel?: boolean;
  className?: string;
};

export function GraphSearchCanvas({
  variant = "hero",
  showLabel = variant === "hero",
  className,
}: GraphSearchCanvasProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  // The faint background version follows the black / ash-white theme
  const { resolvedTheme } = useTheme();
  const paletteName =
    variant === "hero"
      ? "hero"
      : resolvedTheme === "dark"
        ? "subtleDark"
        : "subtleLight";

  useEffect(() => {
    const canvas = canvasRef.current;
    const ctx = canvas?.getContext("2d");
    if (!canvas || !ctx) return;

    const palette = PALETTES[paletteName];
    const reducedMotion = window.matchMedia(
      "(prefers-reduced-motion: reduce)",
    ).matches;
    const stepMs = variant === "hero" ? 75 : 130;
    const traceMs = variant === "hero" ? 110 : 160;

    // Size the graph to the space it has, within sensible bounds.
    const area = canvas.clientWidth * canvas.clientHeight;
    const perNode = variant === "hero" ? 9000 : 16000;
    const nodeCount = Math.round(Math.min(80, Math.max(36, area / perNode)));
    const points = scatterPoints(nodeCount);
    const { edges, links } = buildGraph(points);

    let width = 0;
    let height = 0;
    const resize = () => {
      const dpr = Math.min(window.devicePixelRatio || 1, 2);
      width = canvas.clientWidth;
      height = canvas.clientHeight;
      canvas.width = Math.round(width * dpr);
      canvas.height = Math.round(height * dpr);
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    };
    resize();

    // Canvas text cannot read CSS variables, so take the resolved font.
    const fontFamily = getComputedStyle(canvas).fontFamily || "monospace";

    let algorithmIndex = 0;
    const newSearch = () => {
      const [source, target] = pickEndpoints(links);
      const algorithm = ALGORITHMS[algorithmIndex++ % ALGORITHMS.length];
      return new Search(algorithm, source, target, points, links, edges.length);
    };

    let search = newSearch();
    let phase: Phase = "search";
    let phaseStart = 0;
    let lastStep = 0;
    let traced = 0; // path edges drawn so far

    // Rotation, nudged towards the pointer.
    let yaw = Math.random() * Math.PI * 2;
    const pitch = 0.35;
    let pointerX = 0;
    let pointerY = 0;
    let lookX = 0;
    let lookY = 0;

    const onPointerMove = (event: PointerEvent) => {
      const rect = canvas.getBoundingClientRect();
      if (!rect.width || !rect.height) return;
      pointerX = Math.max(
        -1,
        Math.min(1, ((event.clientX - rect.left) / rect.width) * 2 - 1),
      );
      pointerY = Math.max(
        -1,
        Math.min(1, ((event.clientY - rect.top) / rect.height) * 2 - 1),
      );
    };

    // Projected positions, reused every frame.
    const sx = new Float32Array(nodeCount);
    const sy = new Float32Array(nodeCount);
    const scale = new Float32Array(nodeCount);
    const depth = new Float32Array(nodeCount);
    const drawOrder = Array.from({ length: nodeCount }, (_, i) => i);

    const project = () => {
      const radius =
        Math.min(width, height) * (variant === "hero" ? 0.4 : 0.46);
      const cx = width / 2;
      const cy = height / 2;
      const cosY = Math.cos(yaw + lookX);
      const sinY = Math.sin(yaw + lookX);
      const cosX = Math.cos(pitch + lookY);
      const sinX = Math.sin(pitch + lookY);
      for (let i = 0; i < nodeCount; i++) {
        const p = points[i];
        const x1 = p.x * cosY + p.z * sinY;
        const z1 = -p.x * sinY + p.z * cosY;
        const y2 = p.y * cosX - z1 * sinX;
        const z2 = p.y * sinX + z1 * cosX;
        const s = CAMERA_DISTANCE / (CAMERA_DISTANCE - z2);
        sx[i] = cx + x1 * radius * s;
        sy[i] = cy + y2 * radius * s;
        scale[i] = s;
        depth[i] = (z2 + 1) / 2; // 0 far, 1 near
      }
      drawOrder.sort((a, b) => depth[a] - depth[b]);
    };

    const line = (
      a: number,
      b: number,
      rgb: string,
      alpha: number,
      lineWidth: number,
      upTo = 1,
    ) => {
      ctx.strokeStyle = `rgba(${rgb},${alpha})`;
      ctx.lineWidth = lineWidth;
      ctx.beginPath();
      ctx.moveTo(sx[a], sy[a]);
      ctx.lineTo(
        sx[a] + (sx[b] - sx[a]) * upTo,
        sy[a] + (sy[b] - sy[a]) * upTo,
      );
      ctx.stroke();
    };

    const draw = (now: number, overlay: number) => {
      ctx.clearRect(0, 0, width, height);
      project();

      // The whole graph, faint, fading with depth.
      for (const { a, b } of edges) {
        const d = (depth[a] + depth[b]) / 2;
        line(a, b, palette.edge, palette.edgeAlpha * (0.35 + 0.65 * d), 1);
      }

      // Edges the search has relaxed: a bright flash that settles down.
      edges.forEach(({ a, b }, e) => {
        const litAt = search.edgeLitAt[e];
        if (litAt < 0) return;
        const age = Math.min(1, (now - litAt) / 600);
        const d = (depth[a] + depth[b]) / 2;
        const alpha =
          palette.exploredAlpha * (1.8 - 0.8 * age) * (0.4 + 0.6 * d);
        line(a, b, palette.explored, Math.min(1, alpha) * overlay, 1.2);
      });

      // The path found so far, drawn edge by edge from the source.
      if (traced > 0) {
        if (palette.glow) {
          ctx.shadowColor = `rgba(${palette.path},0.9)`;
          ctx.shadowBlur = 12;
        }
        const partial =
          phase === "trace" ? Math.min(1, (now - lastStep) / traceMs) : 1;
        for (let i = 0; i < traced && i < search.path.length; i++) {
          const a = search.pathNodes[i];
          const b = search.pathNodes[i + 1];
          const upTo = i === traced - 1 && phase === "trace" ? partial : 1;
          line(a, b, palette.path, palette.pathAlpha * overlay, 2.4, upTo);
        }
        ctx.shadowBlur = 0;
      }

      // A packet travelling along the finished path.
      if (
        (phase === "hold" || phase === "fade") &&
        search.pathNodes.length > 1
      ) {
        const segments = search.pathNodes.length - 1;
        const t = (((now - phaseStart) / 1400) % 1) * segments;
        const i = Math.min(segments - 1, Math.floor(t));
        const a = search.pathNodes[i];
        const b = search.pathNodes[i + 1];
        const f = t - i;
        const x = sx[a] + (sx[b] - sx[a]) * f;
        const y = sy[a] + (sy[b] - sy[a]) * f;
        ctx.fillStyle = `rgba(${palette.packet},${(variant === "hero" ? 0.95 : 0.7) * overlay})`;
        if (palette.glow) {
          ctx.shadowColor = `rgba(${palette.path},1)`;
          ctx.shadowBlur = 16;
        }
        ctx.beginPath();
        ctx.arc(x, y, 3.2, 0, Math.PI * 2);
        ctx.fill();
        ctx.shadowBlur = 0;
      }

      // Nodes, far ones first so near ones sit on top.
      const onPath = new Set(
        traced > 0 ? search.pathNodes.slice(0, traced + 1) : [],
      );
      for (const i of drawOrder) {
        const d = depth[i];
        let r = (variant === "hero" ? 2.2 : 1.8) * scale[i];
        let rgb = palette.node;
        let alpha = palette.nodeAlpha * (0.35 + 0.65 * d);

        if (i === search.source || i === search.target) {
          rgb = i === search.source ? palette.source : palette.target;
          alpha = Math.max(alpha, variant === "hero" ? 1 : 0.6);
          r *= 2;
          ctx.strokeStyle = `rgba(${rgb},${0.45 * alpha})`;
          ctx.lineWidth = 1;
          ctx.beginPath();
          ctx.arc(
            sx[i],
            sy[i],
            r + 4 + Math.sin(now / 300) * 1.5,
            0,
            Math.PI * 2,
          );
          ctx.stroke();
        } else if (onPath.has(i)) {
          rgb = palette.path;
          alpha = Math.max(alpha, palette.pathAlpha) * overlay;
          r *= 1.5;
        } else if (search.nodeState[i] === 1) {
          rgb = palette.frontier;
          alpha = Math.max(alpha, variant === "hero" ? 0.9 : 0.45) * overlay;
          r *= 1.4;
        } else if (search.nodeState[i] === 2) {
          rgb = palette.explored;
          alpha = Math.max(alpha, variant === "hero" ? 0.75 : 0.35) * overlay;
          r *= 1.2;
        }

        ctx.fillStyle = `rgba(${rgb},${alpha})`;
        ctx.beginPath();
        ctx.arc(sx[i], sy[i], r, 0, Math.PI * 2);
        ctx.fill();
      }

      if (showLabel) drawLabel(overlay);
    };

    const drawLabel = (overlay: number) => {
      const lines = [`> ${search.algorithm.toLowerCase()}`];
      if (search.pathNodes.length) {
        lines.push(
          `path found · ${search.path.length} hops · length ${search.pathLength().toFixed(2)}`,
        );
      } else {
        lines.push(
          `visited ${search.visited}/${nodeCount} · frontier ${search.open.length}`,
        );
      }
      ctx.font = `12px ${fontFamily}`;
      ctx.textBaseline = "alphabetic";
      const x = 24;
      let y = height - 24 - (lines.length - 1) * 18;
      lines.forEach((text, i) => {
        ctx.fillStyle = `rgba(${palette.label},${(i === 0 ? 0.9 : 0.6) * overlay})`;
        ctx.fillText(text, x, y);
        y += 18;
      });
    };

    /** Moves the animation on: search, trace the path, hold, fade, repeat. */
    const advance = (now: number) => {
      if (phase === "search" && now - lastStep >= stepMs) {
        lastStep = now;
        if (!search.step(now)) {
          phase = search.path.length ? "trace" : "fade";
          phaseStart = now;
        }
      } else if (phase === "trace" && now - lastStep >= traceMs) {
        lastStep = now;
        traced++;
        if (traced > search.path.length) {
          traced = search.path.length;
          phase = "hold";
          phaseStart = now;
        }
      } else if (phase === "hold" && now - phaseStart >= HOLD_MS) {
        phase = "fade";
        phaseStart = now;
      } else if (phase === "fade" && now - phaseStart >= FADE_MS) {
        search = newSearch();
        traced = 0;
        phase = "search";
        phaseStart = now;
      }
    };

    // Reduced motion: run one search to the end and show it, still.
    if (reducedMotion) {
      while (search.step(0)) {
        /* keep stepping */
      }
      traced = search.path.length;
      phase = "trace";
      lastStep = -Infinity;
      draw(0, 1);
      const observer = new ResizeObserver(() => {
        resize();
        draw(0, 1);
      });
      observer.observe(canvas);
      return () => observer.disconnect();
    }

    let frame = 0;
    let previous = 0;
    let visible = true;

    const tick = (now: number) => {
      const dt = Math.min(50, previous ? now - previous : 16);
      previous = now;

      yaw += dt * 0.00009;
      lookX += (pointerX * 0.5 - lookX) * 0.04;
      lookY += (pointerY * 0.3 - lookY) * 0.04;

      advance(now);
      const overlay =
        phase === "fade" ? Math.max(0, 1 - (now - phaseStart) / FADE_MS) : 1;
      draw(now, overlay);
      frame = requestAnimationFrame(tick);
    };

    const start = () => {
      if (frame || !visible || document.hidden) return;
      previous = 0;
      frame = requestAnimationFrame(tick);
    };
    const stop = () => {
      cancelAnimationFrame(frame);
      frame = 0;
    };

    const resizeObserver = new ResizeObserver(resize);
    resizeObserver.observe(canvas);
    const visibilityObserver = new IntersectionObserver(([entry]) => {
      visible = entry.isIntersecting;
      if (visible) start();
      else stop();
    });
    visibilityObserver.observe(canvas);
    const onVisibilityChange = () => (document.hidden ? stop() : start());
    document.addEventListener("visibilitychange", onVisibilityChange);
    window.addEventListener("pointermove", onPointerMove, { passive: true });
    start();

    return () => {
      stop();
      resizeObserver.disconnect();
      visibilityObserver.disconnect();
      document.removeEventListener("visibilitychange", onVisibilityChange);
      window.removeEventListener("pointermove", onPointerMove);
    };
  }, [variant, showLabel, paletteName]);

  return (
    <canvas
      ref={canvasRef}
      aria-hidden="true"
      className={cn("pointer-events-none block h-full w-full", className)}
      style={{ fontFamily: "var(--font-geist-mono), ui-monospace, monospace" }}
    />
  );
}
