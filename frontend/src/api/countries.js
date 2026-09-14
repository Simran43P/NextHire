// Countries the job search can be pointed at.
//
// Two-letter ISO codes, which is what the aggregator takes. Deliberately a
// short list of the markets people actually search rather than all ~250: a
// scrolling wall of countries is harder to use than a list you can read.

export const COUNTRIES = [
  { code: "in", name: "India" },
  { code: "us", name: "United States" },
  { code: "gb", name: "United Kingdom" },
  { code: "ca", name: "Canada" },
  { code: "au", name: "Australia" },
  { code: "de", name: "Germany" },
  { code: "nl", name: "Netherlands" },
  { code: "ie", name: "Ireland" },
  { code: "sg", name: "Singapore" },
  { code: "ae", name: "United Arab Emirates" },
  { code: "fr", name: "France" },
  { code: "es", name: "Spain" },
  { code: "se", name: "Sweden" },
  { code: "ch", name: "Switzerland" },
  { code: "nz", name: "New Zealand" },
  { code: "jp", name: "Japan" },
  { code: "br", name: "Brazil" },
  { code: "za", name: "South Africa" },
];

export const DEFAULT_COUNTRY = "in";

export function countryName(code) {
  return COUNTRIES.find((country) => country.code === code)?.name ?? code;
}
