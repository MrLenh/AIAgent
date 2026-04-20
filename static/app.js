function agentApp() {
  return {
    tab: 'status',
    tabs: [
      { id: 'status',   label: 'Status',    icon: '◉' },
      { id: 'seo',      label: 'SEO Article', icon: '✎' },
      { id: 'listing',  label: 'Listing',   icon: '✦' },
      { id: 'analyze',  label: 'Analysis',  icon: '∴' },
      { id: 'settings', label: 'Settings',  icon: '⚙' },
    ],
    status: { llm_configured: false, env: {} },

    seo: {
      topic: '', primary_keyword: '', secondary_keywords_raw: '',
      audience: 'general readers', word_count: 1200, tone: 'informative and friendly',
      reference: '',
      loading: false, result: null, error: '',
      publishing: false, publishResult: '', publish_status: 'draft',
    },

    listing: {
      platform: 'manual', product_id: null,
      current_title: '', current_description: '',
      primary_keyword: '', target_audience: 'online shoppers',
      attributes_raw: '',
      fetching: false, loading: false, applying: false,
      result: null, error: '', applyResult: '',
    },

    analyze: {
      mode: 'upload', file: null,
      db_url: '', sql: '',
      text: '',
      question: '',
      loading: false, result: '', error: '',
    },

    settings: {
      llm: { provider: '', model: '', api_key: '' },
      shopify: { shop: '', access_token: '' },
      wordpress: { base_url: '', username: '', app_password: '' },
      woocommerce: { base_url: '', consumer_key: '', consumer_secret: '' },
      testResult: {},
      saved: false,
    },

    async init() {
      this.loadSettings();
      await this.refreshStatus();
    },

    async refreshStatus() {
      try {
        const r = await fetch('/api/status');
        this.status = await r.json();
      } catch (e) {
        this.status = { llm_configured: false, env: {} };
      }
    },

    statusItems() {
      const e = this.status.env || {};
      return [
        { key: 'llm',    label: 'LLM provider',  ok: this.status.llm_configured, detail: e.llm_provider || '(none)' },
        { key: 'anth',   label: 'Anthropic key', ok: e.has_anthropic,  detail: e.has_anthropic ? 'configured' : 'missing' },
        { key: 'oai',    label: 'OpenAI key',    ok: e.has_openai,     detail: e.has_openai ? 'configured' : 'missing' },
        { key: 'gem',    label: 'Gemini key',    ok: e.has_gemini,     detail: e.has_gemini ? 'configured' : 'missing' },
        { key: 'shop',   label: 'Shopify',       ok: e.has_shopify,    detail: e.has_shopify ? 'env configured' : 'no env creds' },
        { key: 'wp',     label: 'WordPress',     ok: e.has_wordpress,  detail: e.has_wordpress ? 'env configured' : 'no env creds' },
        { key: 'woo',    label: 'WooCommerce',   ok: e.has_woocommerce, detail: e.has_woocommerce ? 'env configured' : 'no env creds' },
        { key: 'db',     label: 'Database URL',  ok: e.has_database,   detail: e.has_database ? 'configured' : 'missing' },
      ];
    },

    llmPayload() {
      const s = this.settings.llm;
      if (!s.provider && !s.api_key) return null;
      return { provider: s.provider || null, model: s.model || null, api_key: s.api_key || null };
    },

    async postJSON(path, body) {
      const r = await fetch(path, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      });
      const data = await r.json().catch(() => ({}));
      if (!r.ok) throw new Error(data.detail || `HTTP ${r.status}`);
      return data;
    },

    // ---- SEO ----
    async runSEO() {
      this.seo.loading = true; this.seo.error = ''; this.seo.result = null;
      try {
        const sources = this.seo.reference.trim()
          ? [{ type: 'text', content: this.seo.reference }] : [];
        const body = {
          topic: this.seo.topic,
          primary_keyword: this.seo.primary_keyword,
          secondary_keywords: this.seo.secondary_keywords_raw
            .split(',').map(s => s.trim()).filter(Boolean),
          audience: this.seo.audience,
          word_count: this.seo.word_count,
          tone: this.seo.tone,
          sources,
          llm: this.llmPayload(),
        };
        this.seo.result = await this.postJSON('/api/seo-article', body);
      } catch (e) { this.seo.error = e.message; }
      finally { this.seo.loading = false; }
    },

    async publishToWP() {
      const wp = this.settings.wordpress;
      if (!wp.base_url || !wp.username || !wp.app_password) {
        this.seo.publishResult = 'Cần cấu hình WordPress trong Settings';
        return;
      }
      this.seo.publishing = true; this.seo.publishResult = '';
      try {
        const r = await this.postJSON('/api/wordpress/publish', {
          ...wp,
          title: this.seo.result.title,
          content: this.seo.result.body,
          excerpt: this.seo.result.meta_description,
          status: this.seo.publish_status,
        });
        this.seo.publishResult = `Published: ${r.link || r.id || 'ok'}`;
      } catch (e) { this.seo.publishResult = `Error: ${e.message}`; }
      finally { this.seo.publishing = false; }
    },

    // ---- Listing ----
    async fetchProduct() {
      this.listing.fetching = true; this.listing.error = '';
      try {
        if (this.listing.platform === 'shopify') {
          const s = this.settings.shopify;
          const p = await this.postJSON('/api/shopify/product', { ...s, product_id: this.listing.product_id });
          this.listing.current_title = p.title || '';
          this.listing.current_description = p.body_html || '';
          this.listing.attributes_raw = `vendor: ${p.vendor || ''}\ntype: ${p.product_type || ''}\ntags: ${p.tags || ''}`;
        } else if (this.listing.platform === 'woocommerce') {
          const w = this.settings.woocommerce;
          const p = await this.postJSON('/api/woocommerce/product', { ...w, product_id: this.listing.product_id });
          this.listing.current_title = p.name || '';
          this.listing.current_description = p.description || '';
          this.listing.attributes_raw = (p.categories || []).map(c => `category: ${c.name}`).join('\n');
        }
      } catch (e) { this.listing.error = e.message; }
      finally { this.listing.fetching = false; }
    },

    async runListing() {
      this.listing.loading = true; this.listing.error = ''; this.listing.result = null; this.listing.applyResult = '';
      try {
        const attrs = {};
        this.listing.attributes_raw.split('\n').forEach(line => {
          const idx = line.indexOf(':');
          if (idx > 0) attrs[line.slice(0, idx).trim()] = line.slice(idx + 1).trim();
        });
        this.listing.result = await this.postJSON('/api/optimize-listing', {
          current_title: this.listing.current_title,
          current_description: this.listing.current_description,
          product_attributes: attrs,
          primary_keyword: this.listing.primary_keyword || null,
          target_audience: this.listing.target_audience,
          llm: this.llmPayload(),
        });
      } catch (e) { this.listing.error = e.message; }
      finally { this.listing.loading = false; }
    },

    async applyListing() {
      this.listing.applying = true; this.listing.applyResult = '';
      try {
        if (this.listing.platform === 'shopify') {
          const s = this.settings.shopify;
          await this.postJSON('/api/shopify/apply-listing', {
            ...s, product_id: this.listing.product_id, listing: this.listing.result,
          });
          this.listing.applyResult = 'Applied to Shopify';
        } else if (this.listing.platform === 'woocommerce') {
          const w = this.settings.woocommerce;
          await this.postJSON('/api/woocommerce/apply-listing', {
            ...w, product_id: this.listing.product_id, listing: this.listing.result,
          });
          this.listing.applyResult = 'Applied to WooCommerce';
        }
      } catch (e) { this.listing.applyResult = `Error: ${e.message}`; }
      finally { this.listing.applying = false; }
    },

    // ---- Analysis ----
    async runAnalyze() {
      this.analyze.loading = true; this.analyze.error = ''; this.analyze.result = '';
      try {
        if (this.analyze.mode === 'upload') {
          if (!this.analyze.file) throw new Error('Chọn file CSV');
          const fd = new FormData();
          fd.append('question', this.analyze.question);
          fd.append('file', this.analyze.file);
          const s = this.settings.llm;
          if (s.provider) fd.append('provider', s.provider);
          if (s.model) fd.append('model', s.model);
          if (s.api_key) fd.append('api_key', s.api_key);
          const r = await fetch('/api/analyze-upload', { method: 'POST', body: fd });
          const data = await r.json();
          if (!r.ok) throw new Error(data.detail || `HTTP ${r.status}`);
          this.analyze.result = data.report;
        } else {
          let sources;
          if (this.analyze.mode === 'sql') {
            sources = [{ type: 'database', url: this.analyze.db_url, query: this.analyze.sql }];
          } else {
            sources = [{ type: 'text', content: this.analyze.text }];
          }
          const r = await this.postJSON('/api/analyze', {
            question: this.analyze.question, sources, llm: this.llmPayload(),
          });
          this.analyze.result = r.report;
        }
      } catch (e) { this.analyze.error = e.message; }
      finally { this.analyze.loading = false; }
    },

    // ---- Settings ----
    loadSettings() {
      try {
        const s = localStorage.getItem('aiagent.settings');
        if (s) {
          const parsed = JSON.parse(s);
          this.settings = { ...this.settings, ...parsed, testResult: {}, saved: false };
        }
      } catch {}
    },
    saveSettings() {
      const { testResult, saved, ...rest } = this.settings;
      localStorage.setItem('aiagent.settings', JSON.stringify(rest));
      this.settings.saved = true;
      setTimeout(() => { this.settings.saved = false; }, 1500);
    },
    clearSettings() {
      localStorage.removeItem('aiagent.settings');
      this.settings = {
        llm: { provider: '', model: '', api_key: '' },
        shopify: { shop: '', access_token: '' },
        wordpress: { base_url: '', username: '', app_password: '' },
        woocommerce: { base_url: '', consumer_key: '', consumer_secret: '' },
        testResult: {}, saved: false,
      };
    },
    async testPlatform(platform) {
      const creds = this.settings[platform];
      try {
        const r = await this.postJSON('/api/platforms/test', { platform, creds });
        this.settings.testResult = { ...this.settings.testResult, [platform]: r };
      } catch (e) {
        this.settings.testResult = { ...this.settings.testResult, [platform]: { ok: false, error: e.message } };
      }
    },

    copyToClipboard(text) {
      navigator.clipboard.writeText(text);
    },
  };
}
