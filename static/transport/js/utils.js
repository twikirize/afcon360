// Shared utility functions (NO DOM manipulation, just pure functions)
window.AFCON = {
    formatNumber: (n) => new Intl.NumberFormat().format(n),
    formatCurrency: (a) => new Intl.NumberFormat("en-US", { style: "currency", currency: "USD" }).format(a),
    formatDate: (d) => new Date(d).toLocaleString(),
    timeAgo: (d) => {
        const sec = Math.floor((Date.now() - new Date(d)) / 1000);
        const intervals = { year:31536000, month:2592000, week:604800, day:86400, hour:3600, minute:60 };
        for (let u in intervals) {
            const v = Math.floor(sec / intervals[u]);
            if (v >= 1) return `${v} ${u}${v>1?'s':''} ago`;
        }
        return "just now";
    }
};
