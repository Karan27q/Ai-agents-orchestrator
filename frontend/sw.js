importScripts('https://cdn.jsdelivr.net/npm/@babel/standalone@7.24.0/babel.min.js');

self.addEventListener('install', event => {
  event.waitUntil(self.skipWaiting());
});

self.addEventListener('activate', event => {
  event.waitUntil(self.clients.claim());
});

self.addEventListener('fetch', event => {
  const url = new URL(event.request.url);

  // Only intercept JavaScript files from our own origin
  if (
    url.origin === self.location.origin &&
    (url.pathname.endsWith('.js') || url.pathname.endsWith('.jsx')) &&
    !url.pathname.endsWith('sw.js')
  ) {
    event.respondWith(
      fetch(event.request)
        .then(response => {
          if (!response.ok) {
            return response;
          }
          return response.text().then(text => {
            try {
              // Transpile the JSX/JS using Babel
              const transpiled = Babel.transform(text, {
                presets: ['react'],
                plugins: []
              }).code;
              
              return new Response(transpiled, {
                headers: { 'Content-Type': 'application/javascript' }
              });
            } catch (err) {
              console.error('Babel compilation failed for ' + url.pathname, err);
              // Return original text if transpilation fails, to avoid breaking non-JSX files
              return new Response(text, {
                headers: { 'Content-Type': 'application/javascript' }
              });
            }
          });
        })
        .catch(err => {
          // Fallback to network if fetch itself fails
          return fetch(event.request);
        })
    );
  }
});
