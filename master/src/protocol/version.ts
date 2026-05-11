// Protocol version negotiation.
//
// On connect, both sides exchange their supported version ranges.
// The selected version is the highest common minor version.

export interface VersionRange {
  min: string; // "1.0"
  max: string; // "1.1"
}

function parseVersion(v: string): number[] {
  return v.split(".").map(Number);
}

// Negotiate picks the highest mutually supported version.
// Returns null if no compatible version exists.
export function negotiate(local: VersionRange, remote: VersionRange): string | null {
  const lMin = parseVersion(local.min);
  const lMax = parseVersion(local.max);
  const rMin = parseVersion(remote.min);
  const rMax = parseVersion(remote.max);

  // Major version must match.
  if (lMin[0] !== rMin[0] || lMax[0] !== rMax[0]) return null;

  // The overlapping range.
  const selectedMajor = lMin[0];
  const selectedMinor = Math.min(lMax[1], rMax[1]);
  if (selectedMinor < Math.max(lMin[1], rMin[1])) return null;

  return `${selectedMajor}.${selectedMinor}`;
}
