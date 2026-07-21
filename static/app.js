const API = '/api';

function feediverse() {
    return {
        // Navigation state
        currentView: 'timeline',
        viewTitle: 'Feediverse',
        viewHistory: [],

        // Timeline state
        posts: [],
        feeds: [],
        loading: false,
        refreshing: false,
        offset: 0,
        limit: 50,
        hasMore: true,
        sortBy: 'published',

        // Discover state
        discoverUrl: '',
        discovering: false,
        discoveredFeeds: [],
        discoverError: '',
        addedFeed: null,

        // Search state
        searchQuery: '',
        searchResults: [],
        searchTotal: 0,
        searching: false,

        // Feed detail state
        activeFeed: null,
        feedTab: 'posts',
        feedMedia: [],
        feedMediaLoading: false,

        // Post detail
        activePost: null,

        // OPML
        opmlResult: null,

        // --- Init ---
        async init() {
            await this.loadTimeline();
        },

        // --- Navigation ---
        pushView(view) {
            this.viewHistory.push(this.currentView);
            this.currentView = view;
        },

        goBack() {
            if (this.viewHistory.length > 0) {
                this.currentView = this.viewHistory.pop();
            } else {
                this.goHome();
            }
        },

        goHome() {
            this.currentView = 'timeline';
            this.viewTitle = 'Feediverse';
            this.viewHistory = [];
            this.posts = [];
            this.offset = 0;
            this.sortBy = 'published';
            this.loadTimeline();
        },

        goSearch() {
            this.pushView('search');
            this.viewTitle = 'Search';
            this.searchQuery = '';
            this.searchResults = [];
            this.searchTotal = 0;
            this.$nextTick(() => {
                if (this.$refs.searchInput) this.$refs.searchInput.focus();
            });
        },

        // --- Timeline ---
        async loadTimeline() {
            this.loading = true;
            try {
                const res = await fetch(`${API}/timeline?limit=${this.limit}&offset=${this.offset}&sort=${this.sortBy}`);
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

        toggleSort() {
            this.sortBy = this.sortBy === 'published' ? 'added' : 'published';
            this.offset = 0;
            this.posts = [];
            this.loadTimeline();
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

        // --- Search ---
        async doSearch() {
            const q = this.searchQuery.trim();
            if (q.length < 2) {
                this.searchResults = [];
                this.searchTotal = 0;
                return;
            }
            this.searching = true;
            try {
                const res = await fetch(`${API}/search?q=${encodeURIComponent(q)}&limit=50`);
                const data = await res.json();
                this.searchResults = data.posts;
                this.searchTotal = data.total || data.posts.length;
            } catch (e) {
                console.error('Search failed:', e);
            } finally {
                this.searching = false;
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
                const res = await fetch(`${API}/feeds`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ url: this.discoverUrl.trim() }),
                });
                const data = await res.json();
                if (!res.ok) throw new Error(data.detail || 'Failed to discover feeds');

                if (data.feed) {
                    this.addedFeed = data;
                    this.discoverUrl = '';
                    this.loadFeeds();
                    this.offset = 0;
                    this.loadTimeline();
                } else if (data.discovered) {
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

        unfollowFromFeed() {
            if (!this.activeFeed) return;
            const feed = this.activeFeed.feed;
            this.unfollow(feed.id, feed.title);
            this.goBack();
        },

        async openFeed(feedId) {
            this.pushView('feed');
            this.viewTitle = '';
            this.feedTab = 'posts';
            this.feedMedia = [];
            try {
                const res = await fetch(`${API}/feeds/${feedId}`);
                this.activeFeed = await res.json();
                this.viewTitle = this.activeFeed.feed.title;
            } catch (e) {
                console.error('Failed to load feed:', e);
            }
        },

        async loadFeedMedia() {
            if (!this.activeFeed) return;
            if (this.feedMedia.length > 0) return;
            this.feedMediaLoading = true;
            try {
                const res = await fetch(`${API}/feeds/${this.activeFeed.feed.id}/media?limit=60`);
                const data = await res.json();
                this.feedMedia = data.media;
            } catch (e) {
                console.error('Failed to load media:', e);
            } finally {
                this.feedMediaLoading = false;
            }
        },

        // --- OPML ---
        async importOpml(event) {
            const file = event.target.files[0];
            if (!file) return;
            this.opmlResult = null;
            try {
                const text = await file.text();
                const res = await fetch(`${API}/opml/import`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/xml' },
                    body: text,
                });
                const data = await res.json();
                if (!res.ok) throw new Error(data.detail || 'Import failed');
                this.opmlResult = data;
                this.loadFeeds();
                this.offset = 0;
                this.loadTimeline();
            } catch (e) {
                this.opmlResult = { added: 0, failed: 1, errors: [{ error: e.message }] };
            }
            event.target.value = '';
        },

        exportOpml() {
            window.open(`${API}/opml/export`, '_blank');
        },

        // --- Post ---
        openPost(post) {
            this.activePost = post;
            if (post && !post.read_at) {
                this.markRead(post);
            }
        },

        async markRead(post) {
            post.read_at = new Date().toISOString();
            try {
                await fetch(`${API}/posts/${post.id}/read`, { method: 'POST' });
            } catch (e) {
                console.error('Failed to mark read:', e);
            }
        },

        async toggleRead(post) {
            if (post.read_at) {
                post.read_at = null;
                try {
                    await fetch(`${API}/posts/${post.id}/unread`, { method: 'POST' });
                } catch (e) {
                    post.read_at = new Date().toISOString();
                    console.error('Failed to mark unread:', e);
                }
            } else {
                await this.markRead(post);
            }
        },

        async markAllRead() {
            try {
                await fetch(`${API}/mark-all-read`, { method: 'POST' });
                this.posts.forEach(p => p.read_at = p.read_at || new Date().toISOString());
            } catch (e) {
                console.error('Failed to mark all read:', e);
            }
        },

        async openPostById(postId) {
            // Find in current posts or fetch
            let post = this.posts.find(p => p.id === postId);
            if (!post && this.activeFeed) {
                post = this.activeFeed.posts.find(p => p.id === postId);
            }
            if (!post && this.searchResults.length > 0) {
                post = this.searchResults.find(p => p.id === postId);
            }
            if (post) {
                this.openPost(post);
            }
        },

        // --- Content rendering ---
        renderContent(html) {
            if (!html) return '';
            const tmp = document.createElement('div');
            tmp.innerHTML = html;
            // Make all links open in new tab
            tmp.querySelectorAll('a').forEach(a => {
                a.setAttribute('target', '_blank');
                a.setAttribute('rel', 'noopener noreferrer');
            });
            // Add loading="lazy" to all images
            tmp.querySelectorAll('img').forEach(img => {
                img.setAttribute('loading', 'lazy');
                img.onerror = () => { img.style.display = 'none'; };
            });
            return tmp.innerHTML;
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
