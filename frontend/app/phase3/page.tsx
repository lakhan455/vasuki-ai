export default function Phase3Page() {
  const links = [
    { href: '/projects', label: 'Projects & Workspaces' },
    { href: '/files', label: 'My Files' },
    { href: '/images', label: 'Image History' },
    { href: '/owner', label: 'Owner Analytics' },
  ];

  return (
    <main style={{ padding: 24, color: 'white', background: '#212121', minHeight: '100vh' }}>
      <h1 style={{ fontSize: 28, marginBottom: 8 }}>V8 Phase 3 Start</h1>
      <p style={{ color: '#b4b4b4', marginBottom: 20 }}>Quick access to the new Phase 3 screens.</p>
      <div style={{ display: 'grid', gap: 12, maxWidth: 640 }}>
        {links.map((link) => (
          <a key={link.href} href={link.href} style={{ border: '1px solid #3a3a3a', borderRadius: 14, padding: 16, background: '#171717', color: 'white', textDecoration: 'none' }}>
            {link.label}
          </a>
        ))}
      </div>
    </main>
  );
}
