// 一起成长 App 图标：奶油色圆角底上，一株小绿芽从摊开的小书里长出来。
// 只用系统 CoreGraphics/ImageIO 按矢量绘制，不用文字、表情符号、字体符号或外部图片；每个尺寸都从矢量重画，
// 16/32 的轮廓加粗到约 0.6 像素以保住大形，再用系统 iconutil 打成 ICNS。
// 用法：swift packaging/macos/Assets/render_icon.swift [输出目录]（默认 packaging/macos/build/icon-qa，Git 忽略）。
// 输出 AppIcon.png（1024×1024 RGBA）、AppIcon.iconset/（16–512 的 1x/2x 共 10 张）与 AppIcon.icns；
// 核对后把 AppIcon.png、AppIcon.icns 复制回本目录提交，build.sh 把 AppIcon.icns 放进 Contents/Resources。
import CoreGraphics
import Foundation
import ImageIO

func rgb(_ hex: UInt32, _ alpha: CGFloat = 1) -> CGColor {
    CGColor(srgbRed: CGFloat(hex >> 16 & 0xFF) / 255, green: CGFloat(hex >> 8 & 0xFF) / 255, blue: CGFloat(hex & 0xFF) / 255, alpha: alpha)
}

func fill(_ ctx: CGContext, _ path: CGPath, _ colors: [CGColor], _ locations: [CGFloat], from start: CGPoint, to end: CGPoint) {
    let gradient = CGGradient(colorsSpace: CGColorSpace(name: CGColorSpace.sRGB), colors: colors as CFArray, locations: locations)!
    ctx.saveGState()
    ctx.addPath(path)
    ctx.clip()
    ctx.drawLinearGradient(gradient, start: start, end: end, options: [.drawsBeforeStartLocation, .drawsAfterEndLocation])
    ctx.restoreGState()
}

func stroke(_ ctx: CGContext, _ path: CGPath, _ color: CGColor, _ width: CGFloat) {
    ctx.addPath(path)
    ctx.setStrokeColor(color)
    ctx.setLineWidth(width)
    ctx.setLineJoin(.round)
    ctx.setLineCap(.round)
    ctx.strokePath()
}

/// 摊开的书（1024 画布、y 向上）：左半页按参数画，右半页镜像；书脊处下凹，外缘微翘。
func book(outer x: CGFloat, top: CGFloat, bottom: CGFloat, spineTop: CGFloat, spineBottom: CGFloat) -> CGPath {
    let w = 512 - x
    let half = CGMutablePath()
    half.move(to: CGPoint(x: 512, y: spineTop))
    half.addCurve(to: CGPoint(x: x, y: top), control1: CGPoint(x: 512 - 0.24 * w, y: top + 30), control2: CGPoint(x: 512 - 0.7 * w, y: top + 40))
    half.addLine(to: CGPoint(x: x, y: bottom))
    half.addCurve(to: CGPoint(x: 512, y: spineBottom), control1: CGPoint(x: 512 - 0.7 * w, y: bottom + 18), control2: CGPoint(x: 512 - 0.24 * w, y: bottom))
    half.closeSubpath()
    let both = CGMutablePath()
    both.addPath(half)
    both.addPath(half, transform: CGAffineTransform(a: -1, b: 0, c: 0, d: 1, tx: 1024, ty: 0))
    return both
}

/// 叶片：叶柄窄、中段饱满的杏仁形，另返回一条叶脉。
func leaf(from base: CGPoint, to tip: CGPoint, width: CGFloat) -> (blade: CGPath, vein: CGPath) {
    let dx = tip.x - base.x, dy = tip.y - base.y
    let length = (dx * dx + dy * dy).squareRoot()
    func at(_ t: CGFloat, _ side: CGFloat) -> CGPoint {
        CGPoint(x: base.x + dx * t - dy / length * width * side, y: base.y + dy * t + dx / length * width * side)
    }
    let blade = CGMutablePath()
    blade.move(to: base)
    blade.addCurve(to: tip, control1: at(0.15, 0.55), control2: at(0.6, 1.15))
    blade.addCurve(to: base, control1: at(0.6, -1.15), control2: at(0.15, -0.55))
    blade.closeSubpath()
    let vein = CGMutablePath()
    vein.move(to: at(0.12, 0))
    vein.addQuadCurve(to: at(0.78, 0), control: at(0.45, 0.1))
    return (blade, vein)
}

/// 在 px×px 透明画布上按 1024 坐标绘制整枚图标。
func render(_ px: Int) -> CGImage {
    let ctx = CGContext(data: nil, width: px, height: px, bitsPerComponent: 8, bytesPerRow: 0, space: CGColorSpace(name: CGColorSpace.sRGB)!,
                        bitmapInfo: CGImageAlphaInfo.premultipliedLast.rawValue)!
    let s = CGFloat(px) / 1024           // 阴影参数按设备像素计，需随尺寸缩放
    let k = max(1, 51.2 / CGFloat(px))   // 轮廓至少约 0.6 像素
    let detail = px >= 64                // 叶脉、茎高光只在 64 像素及以上画
    ctx.scaleBy(x: s, y: s)

    // 奶油色圆角底：轻投影，上亮下暖，内缘一圈细边；四周留透明边
    let body = CGPath(roundedRect: CGRect(x: 100, y: 100, width: 824, height: 824), cornerWidth: 186, cornerHeight: 186, transform: nil)
    ctx.saveGState()
    ctx.setShadow(offset: CGSize(width: 0, height: -12 * s), blur: 28 * s, color: rgb(0x5A4026, 0.3))
    ctx.addPath(body)
    ctx.setFillColor(rgb(0xF6E3BA))
    ctx.fillPath()
    ctx.restoreGState()
    fill(ctx, body, [rgb(0xFFF8E6), rgb(0xF4DDAF)], [0, 1], from: CGPoint(x: 512, y: 924), to: CGPoint(x: 512, y: 100))
    fill(ctx, body, [rgb(0xFFFFFF, 0.6), rgb(0xFFFFFF, 0)], [0, 1], from: CGPoint(x: 512, y: 924), to: CGPoint(x: 512, y: 660))
    ctx.saveGState()
    ctx.addPath(body)
    ctx.clip()
    stroke(ctx, body, rgb(0xE2C28A), 10 * k)
    ctx.restoreGState()

    // 书与小芽合成一层，整体在底上投下柔和阴影
    let ink = rgb(0x6B4226), leafInk = rgb(0x2C6A2E)
    ctx.saveGState()
    ctx.setShadow(offset: CGSize(width: 0, height: -10 * s), blur: 18 * s, color: rgb(0x7A5230, 0.3))
    ctx.beginTransparencyLayer(auxiliaryInfo: nil)

    let cover = book(outer: 182, top: 498, bottom: 258, spineTop: 448, spineBottom: 218)
    fill(ctx, cover, [rgb(0xD9934F), rgb(0xA8653A)], [0, 1], from: CGPoint(x: 512, y: 540), to: CGPoint(x: 512, y: 218))
    stroke(ctx, cover, ink, 12 * k)
    let stack = book(outer: 198, top: 508, bottom: 280, spineTop: 458, spineBottom: 240)
    fill(ctx, stack, [rgb(0xF3E6C8), rgb(0xE0C99C)], [0, 1], from: CGPoint(x: 512, y: 540), to: CGPoint(x: 512, y: 240))
    stroke(ctx, stack, ink, 8 * k)

    // 茎先画，书页盖住根部，小芽像从书缝里长出来
    let stem = CGMutablePath()
    stem.move(to: CGPoint(x: 512, y: 420))
    stem.addCurve(to: CGPoint(x: 516, y: 640), control1: CGPoint(x: 504, y: 520), control2: CGPoint(x: 524, y: 580))
    stroke(ctx, stem, leafInk, 36 + 24 * k)
    stroke(ctx, stem, rgb(0x5DAA45), 36)
    if detail {
        ctx.saveGState()
        ctx.translateBy(x: -7, y: 0)
        stroke(ctx, stem, rgb(0x96D46E), 11)
        ctx.restoreGState()
    }

    let pages = book(outer: 204, top: 520, bottom: 300, spineTop: 470, spineBottom: 262)
    fill(ctx, pages, [rgb(0xF2E6CB), rgb(0xFFFDF7), rgb(0xF0E2C4), rgb(0xE3D0A8), rgb(0xF0E2C4), rgb(0xFFFDF7), rgb(0xF2E6CB)],
         [0, 0.22, 0.46, 0.5, 0.54, 0.78, 1], from: CGPoint(x: 204, y: 0), to: CGPoint(x: 820, y: 0))
    stroke(ctx, pages, ink, 12 * k)

    // 两片子叶：右片略大，叶面上浅下深
    let leaves: [(CGPoint, CGPoint, CGFloat)] = [(CGPoint(x: 510, y: 626), CGPoint(x: 302, y: 776), 92),
                                                 (CGPoint(x: 518, y: 634), CGPoint(x: 748, y: 812), 104)]
    for (base, tip, width) in leaves {
        let shape = leaf(from: base, to: tip, width: width)
        fill(ctx, shape.blade, [rgb(0xBCE68A), rgb(0x6FB84B), rgb(0x3E8C37)], [0, 0.5, 1], from: CGPoint(x: 512, y: 830), to: CGPoint(x: 512, y: 600))
        stroke(ctx, shape.blade, leafInk, 12 * k)
        if detail { stroke(ctx, shape.vein, rgb(0x3A8233, 0.85), 9) }
    }

    ctx.endTransparencyLayer()
    ctx.restoreGState()
    return ctx.makeImage()!
}

func writePNG(_ image: CGImage, to url: URL) {
    guard let target = CGImageDestinationCreateWithURL(url as CFURL, "public.png" as CFString, 1, nil) else { fatalError("无法写入 \(url.path)") }
    CGImageDestinationAddImage(target, image, nil)
    guard CGImageDestinationFinalize(target) else { fatalError("无法写入 \(url.path)") }
}

let here = URL(fileURLWithPath: #filePath).deletingLastPathComponent()
let out = CommandLine.arguments.count > 1 ? URL(fileURLWithPath: CommandLine.arguments[1]) : here.appendingPathComponent("../build/icon-qa").standardizedFileURL
let iconset = out.appendingPathComponent("AppIcon.iconset")
try FileManager.default.createDirectory(at: iconset, withIntermediateDirectories: true)
writePNG(render(1024), to: out.appendingPathComponent("AppIcon.png"))
for size in [16, 32, 128, 256, 512] {
    writePNG(render(size), to: iconset.appendingPathComponent("icon_\(size)x\(size).png"))
    writePNG(render(size * 2), to: iconset.appendingPathComponent("icon_\(size)x\(size)@2x.png"))
}
let iconutil = Process()
iconutil.executableURL = URL(fileURLWithPath: "/usr/bin/iconutil")
iconutil.arguments = ["-c", "icns", iconset.path, "-o", out.appendingPathComponent("AppIcon.icns").path]
try iconutil.run()
iconutil.waitUntilExit()
guard iconutil.terminationStatus == 0 else { fatalError("iconutil 退出码 \(iconutil.terminationStatus)") }
print(out.appendingPathComponent("AppIcon.png").path)
print(out.appendingPathComponent("AppIcon.icns").path)
