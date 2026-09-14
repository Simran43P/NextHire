import { useMemo, useState } from "react";
import { ArrowRight, Plus, Sparkles, X } from "lucide-react";
import { WarningNotice } from "./ui/ErrorNotice";

/**
 * Review and correct the extracted profile before anything downstream uses it.
 *
 * Extraction is good, not perfect, and every later stage inherits its mistakes:
 * a skill the model missed is a skill the job search never looks for and the
 * ATS analysis marks as missing. One minute of review here is worth more than
 * any amount of prompt tuning.
 */

const GAP_LABELS = {
  name: "name",
  email: "email address",
  skills: "skills",
  education: "education",
  "experience or projects": "work experience or projects",
};

function Field({ label, value, onChange, type = "text", placeholder, flagged }) {
  return (
    <label className="block">
      <span className="text-xs font-medium text-slate-500">{label}</span>
      <input
        type={type}
        value={value ?? ""}
        placeholder={placeholder}
        onChange={(event) => onChange(event.target.value)}
        className={`mt-1 w-full rounded-xl border px-3.5 py-2.5 text-sm text-slate-900 outline-none transition-colors focus:border-blue-400 focus:ring-2 focus:ring-blue-100 ${
          flagged ? "border-amber-300 bg-amber-50/40" : "border-slate-200 bg-white"
        }`}
      />
    </label>
  );
}

function SectionCard({ title, subtitle, children, action }) {
  return (
    <section className="bg-white rounded-2xl border border-slate-100 shadow-sm p-6">
      <div className="flex items-start justify-between gap-4 mb-4">
        <div>
          <h2 className="text-base font-bold text-slate-900">{title}</h2>
          {subtitle && <p className="text-xs text-slate-500 mt-0.5">{subtitle}</p>}
        </div>
        {action}
      </div>
      {children}
    </section>
  );
}

export default function ProfileReview({ profile, gaps = [], onConfirm, onBack }) {
  const [draft, setDraft] = useState(() => structuredClone(profile));
  const [newSkill, setNewSkill] = useState("");

  const set = (key, value) => setDraft((prev) => ({ ...prev, [key]: value }));

  const setListItem = (key, index, field, value) =>
    setDraft((prev) => {
      const list = [...(prev[key] ?? [])];
      list[index] = { ...list[index], [field]: value };
      return { ...prev, [key]: list };
    });

  const removeListItem = (key, index) =>
    setDraft((prev) => ({
      ...prev,
      [key]: (prev[key] ?? []).filter((_, i) => i !== index),
    }));

  const addSkill = () => {
    const value = newSkill.trim();
    if (!value) return;
    const existing = draft.skills ?? [];
    if (existing.some((skill) => skill.toLowerCase() === value.toLowerCase())) {
      setNewSkill("");
      return;
    }
    set("skills", [...existing, value]);
    setNewSkill("");
  };

  const removeSkill = (skill) =>
    set("skills", (draft.skills ?? []).filter((item) => item !== skill));

  const gapMessage = useMemo(() => {
    if (gaps.length === 0) return null;
    const named = gaps.map((gap) => GAP_LABELS[gap] ?? gap);
    const list =
      named.length === 1
        ? named[0]
        : `${named.slice(0, -1).join(", ")} and ${named[named.length - 1]}`;
    return `We could not find your ${list} in the PDF. Adding it here will noticeably improve your matches.`;
  }, [gaps]);

  const skills = draft.skills ?? [];

  return (
    <div className="min-h-screen bg-slate-50">
      <header className="border-b border-slate-100 bg-white">
        <div className="max-w-4xl mx-auto px-6 py-4 flex items-center gap-2">
          <Sparkles className="w-6 h-6 text-blue-500" fill="currentColor" />
          <span className="text-lg font-bold text-slate-900">NextHire</span>
        </div>
      </header>

      <main className="max-w-4xl mx-auto px-6 py-10 pb-32">
        <div className="text-center mb-8">
          <h1 className="text-3xl sm:text-4xl font-extrabold text-slate-900">
            Check what we{" "}
            <span className="bg-clip-text text-transparent bg-gradient-to-r from-blue-600 to-fuchsia-500">
              read
            </span>{" "}
            from your resume
          </h1>
          <p className="text-slate-500 mt-3 max-w-xl mx-auto">
            Everything below drives your job matches and your ATS scores. Fix anything
            that looks wrong now - it is much harder to spot later.
          </p>
        </div>

        {gapMessage && <WarningNotice messages={gapMessage} className="mb-6" />}

        <div className="space-y-6">
          <SectionCard title="About you">
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              <Field
                label="Full name"
                value={draft.name}
                onChange={(value) => set("name", value)}
                flagged={gaps.includes("name")}
                placeholder="Your name"
              />
              <Field
                label="Email"
                type="email"
                value={draft.email}
                onChange={(value) => set("email", value)}
                flagged={gaps.includes("email")}
                placeholder="you@example.com"
              />
              <Field
                label="Phone"
                value={draft.phone}
                onChange={(value) => set("phone", value)}
                placeholder="Optional"
              />
              <Field
                label="Location"
                value={draft.location}
                onChange={(value) => set("location", value)}
                placeholder="City, State"
              />
              <Field
                label="Years of experience"
                type="number"
                value={draft.years_of_experience}
                onChange={(value) =>
                  set("years_of_experience", Number(value) || 0)
                }
              />
            </div>
          </SectionCard>

          <SectionCard
            title="Skills"
            subtitle="The single biggest driver of your job matches. Add anything we missed."
          >
            {gaps.includes("skills") && skills.length === 0 && (
              <p className="text-xs text-amber-700 mb-3">
                No skills were found. Job matching will be poor until you add some.
              </p>
            )}

            <div className="flex flex-wrap gap-2 mb-4">
              {skills.map((skill) => (
                <span
                  key={skill}
                  className="inline-flex items-center gap-1.5 rounded-full bg-blue-50 border border-blue-200 text-blue-700 pl-3 pr-2 py-1 text-sm"
                >
                  {skill}
                  <button
                    type="button"
                    onClick={() => removeSkill(skill)}
                    aria-label={`Remove ${skill}`}
                    className="text-blue-400 hover:text-blue-700 transition-colors"
                  >
                    <X className="w-3.5 h-3.5" />
                  </button>
                </span>
              ))}
              {skills.length === 0 && (
                <span className="text-sm text-slate-400">No skills yet.</span>
              )}
            </div>

            <div className="flex gap-2">
              <input
                value={newSkill}
                onChange={(event) => setNewSkill(event.target.value)}
                onKeyDown={(event) => {
                  if (event.key === "Enter") {
                    event.preventDefault();
                    addSkill();
                  }
                }}
                placeholder="Add a skill and press Enter"
                className="flex-1 rounded-xl border border-slate-200 bg-white px-3.5 py-2.5 text-sm outline-none transition-colors focus:border-blue-400 focus:ring-2 focus:ring-blue-100"
              />
              <button
                type="button"
                onClick={addSkill}
                className="inline-flex items-center gap-1.5 rounded-xl bg-slate-900 text-white px-4 py-2.5 text-sm font-medium hover:bg-slate-800 transition-colors"
              >
                <Plus className="w-4 h-4" />
                Add
              </button>
            </div>
          </SectionCard>

          <SectionCard
            title="Experience"
            subtitle={
              (draft.experience ?? []).length === 0
                ? "Nothing found. That is normal for a fresher - your projects matter more."
                : undefined
            }
          >
            <div className="space-y-4">
              {(draft.experience ?? []).map((entry, index) => (
                <div
                  key={index}
                  className="rounded-xl border border-slate-100 bg-slate-50/60 p-4"
                >
                  <div className="flex justify-end">
                    <button
                      type="button"
                      onClick={() => removeListItem("experience", index)}
                      className="text-xs text-slate-400 hover:text-red-500 transition-colors"
                    >
                      Remove
                    </button>
                  </div>
                  <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
                    <Field
                      label="Company"
                      value={entry.company}
                      onChange={(value) =>
                        setListItem("experience", index, "company", value)
                      }
                    />
                    <Field
                      label="Role"
                      value={entry.designation}
                      onChange={(value) =>
                        setListItem("experience", index, "designation", value)
                      }
                    />
                    <Field
                      label="Duration"
                      value={entry.duration}
                      onChange={(value) =>
                        setListItem("experience", index, "duration", value)
                      }
                    />
                  </div>
                </div>
              ))}
              {(draft.experience ?? []).length === 0 && (
                <p className="text-sm text-slate-400">No work experience listed.</p>
              )}
            </div>
          </SectionCard>

          <SectionCard
            title="Projects"
            subtitle="Where a fresher's real skills live. The technologies here are searched too."
          >
            <div className="space-y-4">
              {(draft.projects ?? []).map((entry, index) => (
                <div
                  key={index}
                  className="rounded-xl border border-slate-100 bg-slate-50/60 p-4"
                >
                  <div className="flex justify-end">
                    <button
                      type="button"
                      onClick={() => removeListItem("projects", index)}
                      className="text-xs text-slate-400 hover:text-red-500 transition-colors"
                    >
                      Remove
                    </button>
                  </div>
                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                    <Field
                      label="Project name"
                      value={entry.name}
                      onChange={(value) => setListItem("projects", index, "name", value)}
                    />
                    <Field
                      label="Technologies (comma separated)"
                      value={(entry.technologies ?? []).join(", ")}
                      onChange={(value) =>
                        setListItem(
                          "projects",
                          index,
                          "technologies",
                          value
                            .split(",")
                            .map((item) => item.trim())
                            .filter(Boolean)
                        )
                      }
                    />
                  </div>
                </div>
              ))}
              {(draft.projects ?? []).length === 0 && (
                <p className="text-sm text-slate-400">No projects listed.</p>
              )}
            </div>
          </SectionCard>

          <SectionCard title="Education">
            <div className="space-y-4">
              {(draft.education ?? []).map((entry, index) => (
                <div
                  key={index}
                  className="rounded-xl border border-slate-100 bg-slate-50/60 p-4"
                >
                  <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
                    <Field
                      label="Degree"
                      value={entry.degree}
                      onChange={(value) =>
                        setListItem("education", index, "degree", value)
                      }
                      flagged={gaps.includes("education")}
                    />
                    <Field
                      label="Institution"
                      value={entry.college}
                      onChange={(value) =>
                        setListItem("education", index, "college", value)
                      }
                    />
                    <Field
                      label="Year"
                      value={entry.year}
                      onChange={(value) => setListItem("education", index, "year", value)}
                    />
                  </div>
                </div>
              ))}
              {(draft.education ?? []).length === 0 && (
                <p className="text-sm text-slate-400">No education listed.</p>
              )}
            </div>
          </SectionCard>
        </div>
      </main>

      <div className="fixed bottom-0 left-0 right-0 border-t border-slate-100 bg-white/90 backdrop-blur">
        <div className="max-w-4xl mx-auto px-6 py-4 flex items-center justify-between gap-4">
          <button
            type="button"
            onClick={onBack}
            className="text-sm font-medium text-slate-500 hover:text-slate-800 transition-colors"
          >
            Upload a different resume
          </button>
          <button
            type="button"
            onClick={() => onConfirm(draft)}
            className="inline-flex items-center gap-2 rounded-full bg-gradient-to-r from-blue-500 to-fuchsia-500 text-white px-7 py-3 text-sm font-medium shadow-lg shadow-purple-500/30 hover:opacity-90 transition-opacity"
          >
            Looks right - find my job titles
            <ArrowRight className="w-4 h-4" />
          </button>
        </div>
      </div>
    </div>
  );
}
