"use client";

/**
 * PaperVisual — original MathPipe 3D paper scene.
 *
 * Built from scratch for MathPipe (no third-party component source used):
 * a translucent document plane textured with real math content (canvas-drawn),
 * floating over a giant integral watermark, with pointer parallax and
 * drag-to-rotate + inertial settling. Single scene, DPR-capped, paused
 * offscreen, static frame under prefers-reduced-motion.
 */

import { useEffect, useRef } from "react";
import * as THREE from "three";

function drawPaperTexture(): HTMLCanvasElement {
  const canvas = document.createElement("canvas");
  canvas.width = 512;
  canvas.height = 680;
  const ctx = canvas.getContext("2d")!;
  // paper
  ctx.fillStyle = "#f4f2ec";
  ctx.fillRect(0, 0, 512, 680);
  ctx.fillStyle = "#2b2721";
  ctx.font = "600 30px Georgia, serif";
  ctx.fillText("Quadratic Equations", 40, 70);
  ctx.fillStyle = "#8a8478";
  ctx.fillRect(40, 88, 432, 2);
  // body lines
  ctx.fillStyle = "#b9b3a6";
  for (let i = 0; i < 4; i++) ctx.fillRect(40, 120 + i * 22, 432 - (i % 2) * 90, 8);
  // equation block
  ctx.fillStyle = "#2b2721";
  ctx.font = "34px Georgia, serif";
  ctx.fillText("x = (−b ± √(b² − 4ac)) / 2a", 52, 250);
  // fraction
  ctx.font = "30px Georgia, serif";
  ctx.fillText("x² + 3x + 2", 120, 330);
  ctx.fillRect(60, 344, 240, 3);
  ctx.fillText("(x + 1)(x + 2)", 92, 388);
  // matrix
  ctx.font = "26px Georgia, serif";
  ctx.fillText("⎡ a  b ⎤", 60, 470);
  ctx.fillText("⎣ c  d ⎦", 60, 505);
  // axes + curve
  ctx.strokeStyle = "#8a8478";
  ctx.lineWidth = 2;
  ctx.beginPath();
  ctx.moveTo(330, 430);
  ctx.lineTo(330, 560);
  ctx.moveTo(300, 530);
  ctx.lineTo(470, 530);
  ctx.stroke();
  ctx.strokeStyle = "#2b6cb0";
  ctx.lineWidth = 4;
  ctx.beginPath();
  for (let x = 0; x <= 140; x += 4) {
    const px = 330 + x;
    const py = 530 - 0.008 * (x - 70) * (x - 70);
    if (x === 0) ctx.moveTo(px, py);
    else ctx.lineTo(px, py);
  }
  ctx.stroke();
  // editable badge
  ctx.fillStyle = "#1a7f4b";
  ctx.font = "600 20px system-ui, sans-serif";
  ctx.fillText("✓ editable in Word", 40, 630);
  return canvas;
}

export function PaperVisual({ className = "" }: { className?: string }) {
  const hostRef = useRef<HTMLDivElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const host = hostRef.current;
    const canvas = canvasRef.current;
    if (!host || !canvas) return undefined;
    const reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

    // WebGL can be unavailable (disabled GPU, old drivers, blocked context).
    // Fall back to a static 2D rendering of the same artwork instead of crashing.
    let renderer: THREE.WebGLRenderer | null = null;
    try {
      renderer = new THREE.WebGLRenderer({ canvas, antialias: true, alpha: true });
    } catch {
      renderer = null;
    }
    if (!renderer || renderer.getContext() === null) {
      const ctx = canvas.getContext("2d");
      if (ctx) {
        const art = drawPaperTexture();
        const draw = () => {
          const rect = host.getBoundingClientRect();
          const dpr = Math.min(window.devicePixelRatio, 2);
          canvas.width = Math.max(1, Math.round(rect.width * dpr));
          canvas.height = Math.max(1, Math.round(rect.height * dpr));
          ctx.clearRect(0, 0, canvas.width, canvas.height);
          const scale = Math.min(canvas.width / art.width, canvas.height / art.height) * 0.92;
          const dw = art.width * scale;
          const dh = art.height * scale;
          ctx.save();
          ctx.translate(canvas.width / 2, canvas.height / 2);
          ctx.rotate(-0.04);
          ctx.drawImage(art, -dw / 2, -dh / 2, dw, dh);
          ctx.restore();
        };
        draw();
        const ro = new ResizeObserver(draw);
        ro.observe(host);
        return () => ro.disconnect();
      }
      return undefined;
    }
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    const scene = new THREE.Scene();
    const camera = new THREE.PerspectiveCamera(38, 1, 0.1, 50);
    camera.position.set(0, 0, 9);

    const texture = new THREE.CanvasTexture(drawPaperTexture());
    texture.colorSpace = THREE.SRGBColorSpace;
    texture.anisotropy = 4;
    const paper = new THREE.Mesh(
      new THREE.PlaneGeometry(3.4, 4.5, 1, 1),
      new THREE.MeshStandardMaterial({
        map: texture,
        transparent: true,
        opacity: 0.96,
        roughness: 0.55,
        metalness: 0.05,
        side: THREE.DoubleSide,
      }),
    );
    scene.add(paper);

    const glow = new THREE.Mesh(
      new THREE.PlaneGeometry(6.5, 6.5),
      new THREE.MeshBasicMaterial({
        color: new THREE.Color(0x1b2c52),
        transparent: true,
        opacity: 0.22,
        depthWrite: false,
      }),
    );
    glow.position.z = -1.6;
    scene.add(glow);

    scene.add(new THREE.AmbientLight(0xffffff, 0.55));
    const key = new THREE.DirectionalLight(0xffffff, 1.6);
    key.position.set(3, 4, 6);
    scene.add(key);
    const rim = new THREE.DirectionalLight(0x6ea8ff, 0.9);
    rim.position.set(-4, 1, -2);
    scene.add(rim);

    let w = 1;
    let h = 1;
    const resize = () => {
      const rect = host.getBoundingClientRect();
      w = Math.max(1, Math.round(rect.width));
      h = Math.max(1, Math.round(rect.height));
      renderer.setSize(w, h, false);
      camera.aspect = w / h;
      camera.updateProjectionMatrix();
    };
    resize();

    // pointer parallax + drag rotate with inertia
    let tx = 0;
    let ty = 0;
    let vx = 0;
    let vy = 0;
    let dragging = false;
    let px = 0;
    let py = 0;
    const onMove = (e: PointerEvent) => {
      const rect = host.getBoundingClientRect();
      const nx = ((e.clientX - rect.left) / rect.width) * 2 - 1;
      const ny = -(((e.clientY - rect.top) / rect.height) * 2 - 1);
      if (dragging) {
        vx = nx - px;
        vy = ny - py;
        tx += vx * 1.4;
        ty += vy * 1.4;
      } else {
        tx += (nx * 0.35 - tx) * 0.06;
        ty += (ny * 0.25 - ty) * 0.06;
      }
      px = nx;
      py = ny;
    };
    const onDown = (e: PointerEvent) => {
      dragging = true;
      vx = 0;
      vy = 0;
      px = ((e.clientX - host.getBoundingClientRect().left) / host.getBoundingClientRect().width) * 2 - 1;
      py = -(((e.clientY - host.getBoundingClientRect().top) / host.getBoundingClientRect().height) * 2 - 1);
      host.setPointerCapture(e.pointerId);
    };
    const onUp = () => {
      dragging = false;
    };
    host.addEventListener("pointermove", onMove, { passive: true });
    host.addEventListener("pointerdown", onDown);
    host.addEventListener("pointerup", onUp);
    host.addEventListener("pointercancel", onUp);

    let frame = 0;
    let visible = true;
    const t0 = performance.now();
    const tick = (now: number) => {
      if (!dragging) {
        tx += vx;
        ty += vy;
        vx *= 0.94;
        vy *= 0.94;
        // settle back toward rest
        tx += (0 - tx) * 0.008;
        ty += (0 - ty) * 0.008;
      }
      const t = reduced ? 0 : (now - t0) / 1000;
      paper.rotation.y = tx + Math.sin(t * 0.4) * 0.08;
      paper.rotation.x = -ty + Math.cos(t * 0.33) * 0.05;
      paper.position.y = Math.sin(t * 0.6) * 0.12;
      renderer.render(scene, camera);
      frame = visible && !document.hidden ? requestAnimationFrame(tick) : 0;
    };

    const ro = new ResizeObserver(resize);
    ro.observe(host);
    const io = new IntersectionObserver(([entry]) => {
      visible = entry?.isIntersecting ?? true;
      if (visible && !frame) {
        resize();
        frame = requestAnimationFrame(tick);
      }
      if (!visible && frame) {
        cancelAnimationFrame(frame);
        frame = 0;
      }
    });
    io.observe(host);
    resize();
    renderer.render(scene, camera);
    if (!reduced) frame = requestAnimationFrame(tick);

    return () => {
      if (frame) cancelAnimationFrame(frame);
      ro.disconnect();
      io.disconnect();
      host.removeEventListener("pointermove", onMove);
      host.removeEventListener("pointerdown", onDown);
      host.removeEventListener("pointerup", onUp);
      host.removeEventListener("pointercancel", onUp);
      texture.dispose();
      paper.geometry.dispose();
      (paper.material as THREE.Material).dispose();
      glow.geometry.dispose();
      (glow.material as THREE.Material).dispose();
      renderer.dispose();
    };
  }, []);

  return (
    <div ref={hostRef} className={`relative ${className}`} style={{ touchAction: "pan-y", cursor: "grab" }}>
      <span
        aria-hidden="true"
        className="pointer-events-none absolute inset-0 flex items-center justify-center font-display text-[22rem] leading-none text-white/[0.04]"
      >
        ∫
      </span>
      <canvas ref={canvasRef} className="relative block h-full w-full" aria-label="Interactive 3D preview of an editable Word document" />
    </div>
  );
}
