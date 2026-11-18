export function safeSameOriginUrl(path: string | null | undefined, baseUrl: string): string | null {
  if (!path || !baseUrl) return null;
  try {
    const base = new URL(baseUrl);
    const target = new URL(path, base.origin + '/');
    if (target.origin !== base.origin) return null;
    if (target.protocol !== 'https:' && target.protocol !== 'http:') return null;
    return target.toString();
  } catch {
    return null;
  }
}

export function imageUri(path: string | null | undefined, baseUrl: string): string | null {
  if (!path) return null;
  try {
    const base = new URL(baseUrl);
    const target = new URL(path, base.origin + '/');
    if (target.protocol === 'https:' && target.hostname) return target.toString();
    const host = target.hostname;
    const privatePreviewHost =
      host === 'localhost' ||
      host === '127.0.0.1' ||
      /^10\./.test(host) ||
      /^192\.168\./.test(host) ||
      /^172\.(1[6-9]|2\d|3[01])\./.test(host);
    if (target.protocol === 'http:' && privatePreviewHost && target.origin === base.origin) {
      return target.toString();
    }
    return null;
  } catch {
    return null;
  }
}

export function feedTypeLabel(type: string): string {
  switch (type) {
    case 'event': return 'EVENT';
    case 'property': return 'STAY';
    case 'transport': return 'MOBILITY';
    case 'ad': return 'SPONSORED';
    case 'system_update': return 'UPDATE';
    case 'post': return 'COMMUNITY';
    default: return 'PAMOJA';
  }
}

export function feedTypeIcon(type: string): string {
  switch (type) {
    case 'event': return '\u{1F3DF}\u{FE0F}';
    case 'property': return '\u{1F3E8}';
    case 'transport': return '\u{1F698}';
    case 'ad': return '\u2728';
    case 'system_update': return '\u{1F514}';
    case 'post': return '\u{1F4AC}';
    default: return '\u{1F30D}';
  }
}