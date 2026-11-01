/** Conservative customer-name hints from explicit buyer email headers only.
 * Untrusted source text never sets identity without an operator click.
 */
export function suggestCustomerFromEmail(text: string): string | null {
  const labels = new Set<string>();
  for (const line of text.slice(0, 4096).split(/\r?\n/).slice(0, 30)) {
    const match = /^\s*(?:company|customer(?:\s+company)?|organization|organisation)\s*:\s*(.{1,120})\s*$/i.exec(line);
    if (!match) continue;
    const value = match[1].trim();
    // Do not confuse an email address, URL, HTML payload or a paragraph with
    // a legal customer name. Anything ambiguous remains entirely manual.
    if (!value || value.length > 100 || /[@<>]/.test(value) || /https?:\/\//i.test(value)) continue;
    labels.add(value);
  }
  return labels.size === 1 ? [...labels][0] : null;
}
