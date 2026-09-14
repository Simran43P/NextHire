
import {
  Sparkles,
  FileText,
  Target,
  MessageSquare,
  BarChart3,
  BookOpen,
  TrendingUp,
  Award,
  CheckCircle2,
  ArrowRight,
  Star,
} from "lucide-react";

function Navbar({ setShowDialog, accountSlot }) {
  return (
    <nav className="flex items-center justify-between py-6 px-8 max-w-7xl mx-auto">
      <div className="flex items-center gap-2">
        <div className="w-9 h-9 rounded-full bg-blue-500 flex items-center justify-center">
          <Sparkles className="w-4 h-4 text-white" fill="white" strokeWidth={1} />
        </div>
        <span className="text-xl font-bold text-slate-900">NextHire</span>
      </div>
      <div className="flex items-center gap-3">
        {accountSlot}
        <button 
          className="bg-blue-500 hover:bg-blue-600 transition-colors text-white rounded-full px-6 py-2.5 font-medium text-sm"
          onClick={() => setShowDialog(true)}
        >
          Get started free
        </button>
      </div>
    </nav>
  );
}

function HeroMockup() {
  return (
    <div className="bg-slate-50 rounded-3xl p-6">
      <div className="grid grid-cols-2 gap-4">
        {/* Resume Score */}
        <div className="bg-white rounded-2xl shadow-sm p-5 border border-slate-100">
          <div className="flex items-center gap-2 mb-4">
            <div className="w-7 h-7 rounded-lg bg-blue-50 flex items-center justify-center">
              <FileText className="w-4 h-4 text-blue-500" />
            </div>
            <span className="text-sm font-medium text-slate-700">Resume Score</span>
          </div>
          <div className="flex flex-col items-center justify-center py-2">
            <div className="relative w-24 h-24">
              <svg className="w-24 h-24 -rotate-90" viewBox="0 0 96 96">
                <circle
                  cx="48"
                  cy="48"
                  r="42"
                  fill="none"
                  stroke="#e2e8f0"
                  strokeWidth="7"
                />
                <circle
                  cx="48"
                  cy="48"
                  r="42"
                  fill="none"
                  stroke="#3b82f6"
                  strokeWidth="7"
                  strokeLinecap="round"
                  strokeDasharray={2 * Math.PI * 42}
                  strokeDashoffset={2 * Math.PI * 42 * (1 - 0.87)}
                />
              </svg>
              <div className="absolute inset-0 flex items-center justify-center">
                <span className="text-2xl font-bold text-slate-900">87</span>
              </div>
            </div>
            <p className="text-xs text-slate-500 mt-3 text-center">
              Strong — 3 improvements
            </p>
          </div>
        </div>

        {/* Job Match */}
        <div className="bg-white rounded-2xl shadow-sm p-5 border border-slate-100">
          <div className="flex items-center gap-2 mb-3">
            <div className="w-7 h-7 rounded-lg bg-green-50 flex items-center justify-center">
              <Target className="w-4 h-4 text-green-500" />
            </div>
            <span className="text-sm font-medium text-slate-700">Job Match</span>
          </div>
          <p className="text-2xl font-bold text-green-500">94%</p>
          <p className="text-xs text-slate-500 mb-3">Senior Product Designer</p>
          <ul className="space-y-1.5">
            {["UX Research", "Figma", "Design Systems"].map((item) => (
              <li key={item} className="flex items-center gap-1.5 text-xs text-slate-600">
                <CheckCircle2 className="w-3.5 h-3.5 text-green-500 flex-shrink-0" />
                {item}
              </li>
            ))}
          </ul>
        </div>

        {/* Cover Letter */}
        <div className="bg-white rounded-2xl shadow-sm p-5 border border-slate-100">
          <div className="flex items-center gap-2 mb-4">
            <div className="w-7 h-7 rounded-lg bg-purple-50 flex items-center justify-center">
              <MessageSquare className="w-4 h-4 text-purple-500" />
            </div>
            <span className="text-sm font-medium text-slate-700">Cover Letter</span>
          </div>
          <div className="space-y-2 mb-4">
            <div className="h-2 rounded-full bg-purple-100 w-full" />
            <div className="h-2 rounded-full bg-purple-100 w-4/5" />
            <div className="h-2 rounded-full bg-purple-100 w-3/5" />
          </div>
          <span className="inline-block bg-purple-50 text-purple-500 text-xs font-medium px-3 py-1 rounded-full">
            AI writing...
          </span>
        </div>

        {/* Applications */}
        <div className="bg-white rounded-2xl shadow-sm p-5 border border-slate-100">
          <div className="flex items-center gap-2 mb-4">
            <div className="w-7 h-7 rounded-lg bg-orange-50 flex items-center justify-center">
              <BarChart3 className="w-4 h-4 text-orange-500" />
            </div>
            <span className="text-sm font-medium text-slate-700">Applications</span>
          </div>
          <ul className="space-y-2.5">
            <li className="flex items-center justify-between">
              <span className="text-xs text-slate-700">Figma</span>
              <span className="text-[11px] font-medium bg-green-50 text-green-600 px-2 py-0.5 rounded-full">
                Interview
              </span>
            </li>
            <li className="flex items-center justify-between">
              <span className="text-xs text-slate-700">Linear</span>
              <span className="text-[11px] font-medium bg-blue-50 text-blue-600 px-2 py-0.5 rounded-full">
                Applied
              </span>
            </li>
            <li className="flex items-center justify-between">
              <span className="text-xs text-slate-700">Vercel</span>
              <span className="text-[11px] font-medium bg-orange-50 text-orange-600 px-2 py-0.5 rounded-full">
                Offer
              </span>
            </li>
          </ul>
        </div>
      </div>
    </div>
  );
}

function Hero({ setShowDialog }) {
  return (
    <section className="max-w-7xl mx-auto px-8 py-16">
      <div className="grid md:grid-cols-2 gap-12 items-center">
        <div>
          <span className="inline-flex items-center gap-1.5 bg-blue-50 text-blue-600 rounded-full px-4 py-1.5 text-sm font-medium">
            <Sparkles className="w-3.5 h-3.5" />
            AI-powered job search · Now in beta
          </span>

          <h1 className="text-5xl md:text-6xl font-extrabold tracking-tight text-slate-900 mt-6 leading-[1.1]">
            Apply smarter with your{" "}
            <span className="bg-clip-text text-transparent bg-gradient-to-r from-blue-500 to-purple-500">
              AI job application
            </span>{" "}
            assistant
          </h1>

          <p className="text-lg text-slate-500 leading-relaxed mt-6">
            Tailor resumes, generate cover letters, track applications, and
            prepare for interviews — all in one playful AI-powered workspace.
          </p>

          <button 
          onClick={() => setShowDialog(true)}
          className="inline-flex items-center gap-2 bg-gradient-to-r from-blue-500 to-purple-500 hover:opacity-90 transition-opacity text-white rounded-full px-8 py-3.5 mt-8 font-medium">
            Start applying smarter
            <ArrowRight className="w-4 h-4" />
          </button>

          <div className="flex gap-8 mt-12">
            <div>
              <p className="text-2xl font-bold text-slate-900">12k+</p>
              <p className="text-sm text-slate-500">Job seekers</p>
            </div>
            <div>
              <p className="text-2xl font-bold text-slate-900">94%</p>
              <p className="text-sm text-slate-500">Match accuracy</p>
            </div>
            <div>
              <p className="text-2xl font-bold text-slate-900">3x</p>
              <p className="text-sm text-slate-500">More interviews</p>
            </div>
          </div>
        </div>

        <HeroMockup />
      </div>
    </section>
  );
}

const FEATURES = [
  {
    icon: FileText,
    title: "AI Resume Tailoring",
    desc: "Automatically adapt your resume to each job description. Highlight the right skills, keywords, and achievements to pass ATS filters.",
    bg: "bg-blue-50",
    color: "text-blue-500",
  },
  {
    icon: Target,
    title: "Job Match Analysis",
    desc: "Get an instant match score for any job posting. See exactly which requirements you meet and what gaps to bridge.",
    bg: "bg-green-50",
    color: "text-green-500",
  },
  {
    icon: MessageSquare,
    title: "Cover Letter Generator",
    desc: "Generate personalized, compelling cover letters in seconds. Choose your tone — professional, friendly, or bold.",
    bg: "bg-purple-50",
    color: "text-purple-500",
  },
  {
    icon: BarChart3,
    title: "Application Tracker",
    desc: "Keep all your applications organized in one kanban board. Never lose track of deadlines, contacts, or follow-ups.",
    bg: "bg-red-50",
    color: "text-red-500",
  },
  {
    icon: BookOpen,
    title: "Interview Prep",
    desc: "Practice with AI-generated questions tailored to your target role and company.",
    bg: "bg-amber-50",
    color: "text-amber-500",
  },
  {
    icon: TrendingUp,
    title: "AI Suggestions",
    desc: "Get actionable tips to improve your resume score and increase response rates.",
    bg: "bg-purple-50",
    color: "text-purple-500",
  },
  {
    icon: Award,
    title: "Skills Gap Analysis",
    desc: "Identify which skills to learn to become a top candidate for your dream job.",
    bg: "bg-red-50",
    color: "text-red-500",
  },
];

function FeatureCard({ icon: Icon, title, desc, bg, color }) {
  return (
    <div className="bg-white border border-slate-100 rounded-2xl shadow-sm p-6">
      <div className={`w-10 h-10 rounded-xl ${bg} flex items-center justify-center`}>
        <Icon className={`w-5 h-5 ${color}`} />
      </div>
      <h3 className="text-lg font-bold text-slate-900 mt-6 mb-2">{title}</h3>
      <p className="text-sm text-slate-500 leading-relaxed">{desc}</p>
    </div>
  );
}

function Features() {
  const row1 = FEATURES.slice(0, 4);
  const row2 = FEATURES.slice(4);

  return (
    <section className="max-w-7xl mx-auto px-8 py-24">
      <div className="text-center max-w-2xl mx-auto">
        <span className="inline-flex items-center gap-1.5 bg-purple-50 text-purple-600 rounded-full px-4 py-1.5 text-sm font-medium">
          <Sparkles className="w-3.5 h-3.5" />
          Everything you need
        </span>
        <h2 className="text-4xl font-bold text-slate-900 mt-6">
          Your whole job search, supercharged
        </h2>
        <p className="text-slate-500 mt-4">
          From resume tailoring to interview prep — NextHire handles the
          heavy lifting so you can focus on landing the role.
        </p>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6 mt-16">
        {row1.map((f) => (
          <FeatureCard key={f.title} {...f} />
        ))}
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-6 mt-6 max-w-4xl mx-auto">
        {row2.map((f) => (
          <FeatureCard key={f.title} {...f} />
        ))}
      </div>
    </section>
  );
}

function CTA({ setShowDialog }) {
  return (
    <section className="max-w-6xl mx-auto px-8 mt-8 mb-12">
      <div className="relative w-full rounded-3xl overflow-hidden bg-gradient-to-r from-blue-500 via-purple-500 to-pink-500 px-8 py-16 md:p-20 text-center">
        <Sparkles className="absolute top-8 left-8 w-8 h-8 text-white/25" />
        <Star className="absolute bottom-8 right-8 w-9 h-9 text-white/25" fill="currentColor" />

        <h2 className="text-4xl font-bold text-white mb-4">
          Ready to land your dream job?
        </h2>
        <p className="text-lg text-white/90 max-w-xl mx-auto mb-8">
          Join 12,000+ job seekers who use NextHire to apply smarter and get
          more interviews.
        </p>
        <button
          className="inline-flex items-center gap-2 bg-white text-blue-600 rounded-full px-8 py-3.5 font-medium hover:bg-slate-50 transition-colors"
          onClick={() => setShowDialog(true)}
        >
          Start for free — no card required
          <ArrowRight className="w-4 h-4" />
        </button>
      </div>
    </section>
  );
}

export default function NextHireLanding({ setShowDialog, accountSlot }) {
  return (
    <div className="min-h-screen bg-white font-sans antialiased">
      <Navbar setShowDialog={setShowDialog} accountSlot={accountSlot} />
      <Hero setShowDialog={setShowDialog} />
      <Features />
      <CTA setShowDialog={setShowDialog} />
    </div>
  );
}