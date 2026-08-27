const FILENAME_PATTERN = /filename\*=UTF-8''([^;]+)/i
const FILENAME_PLAIN = /filename="?([^";]+)"?/i

/** 从 Content-Disposition 解析文件名；优先 RFC 5987 的 filename*=UTF-8''… */
export function filenameFromDisposition(
  disposition: string | null,
  fallback: string,
): string {
  if (!disposition) return fallback
  const encoded = FILENAME_PATTERN.exec(disposition)
  if (encoded?.[1]) {
    try {
      return decodeURIComponent(encoded[1])
    } catch {
      return encoded[1]
    }
  }
  const plain = FILENAME_PLAIN.exec(disposition)
  return plain?.[1] ? plain[1] : fallback
}

/** Blob + 临时链接触发浏览器下载，用完立刻释放 object URL */
export function saveBlob(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob)
  try {
    const anchor = document.createElement('a')
    anchor.href = url
    anchor.download = filename
    anchor.click()
  } finally {
    URL.revokeObjectURL(url)
  }
}
