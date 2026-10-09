/* The ribbon's body drawn as silk. Each strand is a strip of geometry swept
   along the route's spine in WebGL and rolled about the spine where the route
   twists it, so a curation really turns the ribbon over; a soft room and one
   key light reach it through a sheen material, the shading cloth gets, and the
   turns catch the light. The SVG laid over the canvas keeps every mark, label
   and click; this layer only paints. A slow roll travels along each leg so the
   ribbon drifts like silk in air, unless the reader asked for reduced motion.
   The camera looks straight down, so a point of the strip lands on the same
   pixel as the same point of the SVG layout. */

import * as THREE from 'three'
import { RoomEnvironment } from 'three/examples/jsm/environments/RoomEnvironment.js'

import { pointAt } from './geometry'

import type { Spine } from './geometry'

export interface Body {
  spine: Spine
  /** The ribbon's full width at an arc length. */
  width: (s: number) => number
  /** Its roll about the spine at an arc length, in radians. */
  roll: (s: number) => number
  /** How opaque the ribbon is at an arc length, so a finished run can trail off. */
  alpha: (s: number) => number
}

export interface SilkLeg {
  from: number
  to: number
  strands: { surface: string; count: number }[]
}

/** The fill of each surface's strand, as the page resolved it. */
export type Palette = Record<string, { color: string; alpha: number }>

const STEP = 2
const SEAM = 0.9
const DRIFT = 0.3
const LIFT = 9
const FADED = 0.16

interface Strip {
  mesh: THREE.Mesh
  lo: number
  hi: number
  samples: { x: number; y: number; tx: number; ty: number; nx: number; ny: number; s: number; w: number; roll: number; along: number }[]
}

function srgb(text: string): THREE.Color {
  const color = new THREE.Color()
  const match = /color\(srgb\s+([\d.e-]+)\s+([\d.e-]+)\s+([\d.e-]+)/.exec(text)
  if (match) return color.setRGB(Number(match[1]), Number(match[2]), Number(match[3]), THREE.SRGBColorSpace)
  return color.setStyle(text)
}

export class Silk {
  private renderer: THREE.WebGLRenderer
  private scene = new THREE.Scene()
  private camera = new THREE.OrthographicCamera(0, 1, 0, -1, -400, 400)
  private environment: THREE.Texture
  private legs: { material: THREE.MeshPhysicalMaterial; strips: Strip[]; target: number }[] = []
  private frame = 0
  private start = performance.now()
  private moving: boolean

  constructor(canvas: HTMLCanvasElement) {
    this.renderer = new THREE.WebGLRenderer({ canvas, antialias: true, alpha: true })
    this.renderer.setClearColor(0x000000, 0)
    this.renderer.setPixelRatio(Math.min(2, window.devicePixelRatio || 1))
    this.renderer.toneMapping = THREE.NeutralToneMapping
    const pmrem = new THREE.PMREMGenerator(this.renderer)
    this.environment = pmrem.fromScene(new RoomEnvironment(), 0.04).texture
    pmrem.dispose()
    this.scene.environment = this.environment
    this.scene.environmentIntensity = 1
    const key = new THREE.DirectionalLight(0xffffff, 1.25)
    key.position.set(-0.45, 0.75, 1)
    this.scene.add(key)
    this.moving = !window.matchMedia?.('(prefers-reduced-motion: reduce)').matches
  }

  draw(body: Body, legs: SilkLeg[], palette: Palette, width: number, height: number): void {
    this.clear()
    this.renderer.setSize(width, height, false)
    Object.assign(this.camera, { left: 0, right: width, top: 0, bottom: -height })
    this.camera.updateProjectionMatrix()
    for (const leg of legs) {
      const material = new THREE.MeshPhysicalMaterial({
        vertexColors: true,
        roughness: 0.52,
        sheen: 1,
        sheenRoughness: 0.42,
        sheenColor: new THREE.Color(0.6, 0.58, 0.54),
        clearcoat: 0.12,
        clearcoatRoughness: 0.4,
        side: THREE.DoubleSide,
        transparent: true,
      })
      const total = leg.strands.reduce((sum, strand) => sum + strand.count, 0)
      const strips: Strip[] = []
      if (total && leg.to > leg.from) {
        const stops: number[] = []
        for (let s = leg.from; s < leg.to; s += STEP) stops.push(s)
        stops.push(leg.to)
        const span = leg.to - leg.from
        const samples = stops.map((s) => {
          const p = pointAt(body.spine, s)
          return { x: p.x, y: p.y, tx: p.ny, ty: -p.nx, nx: p.nx, ny: p.ny, s, w: body.width(s), roll: body.roll(s), along: (s - leg.from) / span }
        })
        let before = 0
        for (const strand of leg.strands) {
          const paint = palette[strand.surface] ?? palette.other
          const color = srgb(paint.color)
          const geometry = new THREE.BufferGeometry()
          const n = samples.length
          geometry.setAttribute('position', new THREE.BufferAttribute(new Float32Array(n * 6), 3))
          geometry.setAttribute('normal', new THREE.BufferAttribute(new Float32Array(n * 6), 3))
          const colors = new Float32Array(n * 8)
          samples.forEach((sample, i) => {
            const a = paint.alpha * body.alpha(sample.s)
            colors.set([color.r, color.g, color.b, a, color.r, color.g, color.b, a], i * 8)
          })
          geometry.setAttribute('color', new THREE.BufferAttribute(colors, 4))
          const index: number[] = []
          for (let i = 0; i < n - 1; i++) index.push(i * 2, i * 2 + 1, i * 2 + 2, i * 2 + 1, i * 2 + 3, i * 2 + 2)
          geometry.setIndex(index)
          const mesh = new THREE.Mesh(geometry, material)
          mesh.frustumCulled = false
          this.scene.add(mesh)
          strips.push({ mesh, lo: before / total, hi: (before + strand.count) / total, samples })
          before += strand.count
        }
      }
      this.legs.push({ material, strips, target: 1 })
    }
    this.shape(0)
    this.loop()
  }

  /** Fade every leg but `leg`; null brings them all back. */
  focus(leg: number | null): void {
    this.legs.forEach((item, i) => { item.target = leg === null || leg === i ? 1 : FADED })
    if (!this.moving) {
      for (const item of this.legs) item.material.opacity = item.target
      this.render()
    }
  }

  dispose(): void {
    cancelAnimationFrame(this.frame)
    this.clear()
    this.environment.dispose()
    this.renderer.dispose()
  }

  private clear(): void {
    cancelAnimationFrame(this.frame)
    for (const leg of this.legs) {
      for (const strip of leg.strips) {
        this.scene.remove(strip.mesh)
        strip.mesh.geometry.dispose()
      }
      leg.material.dispose()
    }
    this.legs = []
  }

  /* Lay every strip at time `t`. The drift is a roll and a rise travelling
     along the leg, held to nothing at the leg's ends so the twists stay where
     the layout put them. */
  private shape(t: number): void {
    for (const leg of this.legs) {
      for (const strip of leg.strips) {
        const position = strip.mesh.geometry.getAttribute('position') as THREE.BufferAttribute
        const normal = strip.mesh.geometry.getAttribute('normal') as THREE.BufferAttribute
        const p = position.array as Float32Array
        const q = normal.array as Float32Array
        strip.samples.forEach((sample, i) => {
          const hold = Math.sin(Math.PI * sample.along)
          const wave = sample.s / 150 - t * 0.7
          const roll = sample.roll + DRIFT * hold * Math.sin(wave)
          const z = LIFT * hold * Math.sin(wave * 0.8 + 1.3)
          const dz = (LIFT * hold * Math.cos(wave * 0.8 + 1.3) * 0.8) / 150
          const tx = sample.tx
          const ty = -sample.ty
          const tm = Math.hypot(tx, ty, dz)
          const c = Math.cos(roll)
          const s = Math.sin(roll)
          const dx = c * sample.nx
          const dy = -c * sample.ny
          const dzz = s
          let nx = dy * (dz / tm) - dzz * (ty / tm)
          let ny = dzz * (tx / tm) - dx * (dz / tm)
          let nz = dx * (ty / tm) - dy * (tx / tm)
          const m = Math.hypot(nx, ny, nz) || 1
          nx /= m
          ny /= m
          nz /= m
          const w = sample.w
          const seam = Math.min(SEAM / Math.max(w, 1), (strip.hi - strip.lo) * 0.3) / 2
          const lo = strip.lo + (strip.lo > 0 ? seam : 0) - 0.5
          const hi = strip.hi - (strip.hi < 1 ? seam : 0) - 0.5
          const y = -sample.y
          p.set([sample.x + dx * w * lo, y + dy * w * lo, z + dzz * w * lo, sample.x + dx * w * hi, y + dy * w * hi, z + dzz * w * hi], i * 6)
          q.set([nx, ny, nz, nx, ny, nz], i * 6)
        })
        position.needsUpdate = true
        normal.needsUpdate = true
      }
    }
  }

  private render(): void {
    this.renderer.render(this.scene, this.camera)
  }

  private loop(): void {
    let last = 0
    const tick = (now: number) => {
      this.frame = requestAnimationFrame(tick)
      if (now - last < 33 || document.hidden) return
      last = now
      for (const leg of this.legs) leg.material.opacity += (leg.target - leg.material.opacity) * 0.2
      this.shape((now - this.start) / 1000)
      this.render()
    }
    if (this.moving) this.frame = requestAnimationFrame(tick)
    else this.render()
  }
}
