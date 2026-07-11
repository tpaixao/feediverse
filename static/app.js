const API = '/api';

function feediverse() {
    return {
        // State
        currentView: 'timeline',
        viewTitle: 'Feediverse',
        posts: [],
        feeds: [],
        loading: false,
        refreshing: false,
        offset: 0,
        limit: 50,
        hasMore: true,

        // Discover
        discoverUrl: '',
        discovering: false,
        discoveredFeeds: [],
        discoverError: '',
        addedFeed: null,

        // Detail views
        activeFeed: null,
        activePost: null,

        // --- Init ---
        async init() {
            await this.loadTimeline();
        },

        // --- Navigation ---
        goHome() {
            this.currentView = 'timeline';
            this.viewTitle = 'Feediverse';
            this.posts = [];
            this.offset = 0;
            this.loadTimeline();
        },

        // --- Timeline ---
        async loadTimeline() {
            this.loading = true;
            try {
                const res = await fetch(`${API}/timeline?limit=${this.limit}&offset=${this.offset}`);
                const data = await res.json();
                if (this.offset === 0) {
                    this.posts = data.posts;
                } else {
                    this.posts.push(...data.posts);
                }
                this.hasMore = data.posts.length === this.limit;
            } catch (e) {
                console.error('Failed to load timeline:', e);
            } finally {
                this.loading = false;
            }
        },

        async loadMore() {
            this.offset += this.limit;
            await this.loadTimeline();
        },

        async refresh() {
            this.refreshing = true;
            try {
                await fetch(`${API}/refresh`, { method: 'POST' });
                this.offset = 0;
                await this.loadTimeline();
            } catch (e) {
                console.error('Refresh failed:', e);
            } finally {
                this.refreshing = false;
            }
        },

        // --- Explore / Feeds ---
        async loadFeeds() {
            try {
                const res = await fetch(`${API}/feeds`);
                this.feeds = await res.json();
            } catch (e) {
                console.error('Failed to load feeds:', e);
            }
        },

        async doDiscover() {
            if (!this.discoverUrl.trim()) return;
            this.discovering = true;
            this.discoverError = '';
            this.discoveredFeeds = [];
            this.addedFeed = null;
            try {
                // Try adding directly first (handles single-feed auto-add)
                const res = await fetch(`${API}/feeds`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ url: this.discoverUrl.trim() }),
                });
                const data = await res.json();
                if (!res.ok) throw new Error(data.detail || 'Failed to discover feeds');

                if (data.feed) {
                    // Single feed auto-added
                    this.addedFeed = data;
                    this.discoverUrl = '';
                    this.loadFeeds();
                    this.offset = 0;
                    this.loadTimeline();
                } else if (data.discovered) {
                    // Multiple feeds found — show options
                    this.discoveredFeeds = data.discovered;
                }
            } catch (e) {
                this.discoverError = e.message;
            } finally {
                this.discovering = false;
            }
        },

        async addFeedDirect(url) {
            this.discovering = true;
            this.discoverError = '';
            try {
                const res = await fetch(`${API}/feeds/add-direct`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ url }),
                });
                const data = await res.json();
                if (!res.ok) throw new Error(data.detail || 'Failed to add feed');
                this.addedFeed = data;
                this.discoveredFeeds = [];
                this.discoverUrl = '';
                this.loadFeeds();
                this.offset = 0;
                this.loadTimeline();
            } catch (e) {
                this.discoverError = e.message;
            } finally {
                this.discovering = false;
            }
        },

        async unfollow(feedId, feedTitle) {
            if (!confirm(`Unfollow ${feedTitle}?`)) return;
            try {
                await fetch(`${API}/feeds/${feedId}`, { method: 'DELETE' });
                this.feeds = this.feeds.filter(f => f.id !== feedId);
                this.offset = 0;
                this.loadTimeline();
            } catch (e) {
                console.error('Unfollow failed:', e);
            }
        },

        async openFeed(feedId) {
            this.currentView = 'feed';
            this.viewTitle = '';
            try {
                const res = await fetch(`${API}/feeds/${feedId}`);
                this.activeFeed = await res.json();
                this.viewTitle = this.activeFeed.feed.title;
            } catch (e) {
                console.error('Failed to load feed:', e);
            }
        },

        // --- Post ---
        openPost(post) {
            this.activePost = post;
        },

        // --- Helpers ---
        openUrl(url) {
            if (url) window.open(url, '_blank');
        },

        formatDate(dateStr) {
            if (!dateStr) return '';
            const d = new Date(dateStr);
            const now = new Date();
            const diff = (now - d) / 1000;
            if (diff < 60) return 'just now';
            if (diff < 3600) return `${Math.floor(diff / 60)}m`;
            if (diff < 86400) return `${Math.floor(diff / 3600)}h`;
            if (diff < 604800) return `${Math.floor(diff / 86400)}d`;
            return d.toLocaleDateString();
        },

        stripHtml(html) {
            const tmp = document.createElement('div');
            tmp.innerHTML = html || '';
            return tmp.textContent || tmp.innerText || '';
        },
    };
}