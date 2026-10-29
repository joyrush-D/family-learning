/** 以图片宽高为 1 的相对坐标表示的矩形区域 */
export interface ImageRegion {
    x: number;
    y: number;
    width: number;
    height: number;
}

/** 规范化拖拽得到的两个角点为矩形，并限制在图片范围内 */
/** 待裁剪图片只来自本地文件生成的 blob/data 地址，其他地址一律不渲染 */
export function toSafeImageSrc(src: string): string | undefined {
    return /^(blob:|data:image\/)/i.test(src) ? src : undefined;
}

export function regionFromPoints(ax: number, ay: number, bx: number, by: number): ImageRegion {
    const clamp = (value: number) => Math.min(1, Math.max(0, value));
    const x1 = clamp(Math.min(ax, bx));
    const y1 = clamp(Math.min(ay, by));
    const x2 = clamp(Math.max(ax, bx));
    const y2 = clamp(Math.max(ay, by));
    return { x: x1, y: y1, width: x2 - x1, height: y2 - y1 };
}

/** 按原图分辨率裁剪出各区域，返回 JPEG 图片 */
export async function cropImageRegions(image: HTMLImageElement, regions: ImageRegion[]): Promise<Blob[]> {
    const { naturalWidth, naturalHeight } = image;
    return Promise.all(regions.map((region) => new Promise<Blob>((resolve, reject) => {
        const canvas = document.createElement("canvas");
        const sx = Math.round(region.x * naturalWidth);
        const sy = Math.round(region.y * naturalHeight);
        canvas.width = Math.max(1, Math.round(region.width * naturalWidth));
        canvas.height = Math.max(1, Math.round(region.height * naturalHeight));
        const ctx = canvas.getContext("2d");
        if (!ctx) {
            reject(new Error("Canvas is not supported"));
            return;
        }
        ctx.drawImage(image, sx, sy, canvas.width, canvas.height, 0, 0, canvas.width, canvas.height);
        canvas.toBlob((blob) => (blob ? resolve(blob) : reject(new Error("Canvas is empty"))), "image/jpeg", 0.95);
    })));
}
