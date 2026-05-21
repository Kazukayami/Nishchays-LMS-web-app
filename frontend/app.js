const API = "/api";
const app = document.getElementById("app");

const state = {
  user: null,
  ready: false,
  filters: { category: "All", level: "All", q: "" },
  quizAnswers: {},
  quizCache: {},
  generatedQuiz: null,
};

const esc = (v = "") =>
  String(v)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");

async function request(path, options = {}) {
  const res = await fetch(API + path, {
    credentials: "include",
    headers: { "Content-Type": "application/json", ...(options.headers || {}) },
    ...options,
  });
  if (!res.ok) {
    let message = res.statusText;
    try {
      const data = await res.json();
      message = data.detail || message;
    } catch (_) {}
    throw new Error(Array.isArray(message) ? message.map((m) => m.msg || m).join(", ") : message);
  }
  return res.json();
}

async function loadMe() {
  try {
    state.user = await request("/auth/me");
  } catch (_) {
    state.user = null;
  }
  state.ready = true;
}

function route() {
  return location.hash.replace(/^#/, "") || "/";
}

function go(path) {
  location.hash = path;
}

function nav() {
  const user = state.user;
  return `
    <header class="nav">
      <div class="nav-inner">
        <a class="brand" href="#/">
          <span class="brand-mark">A</span>
          <span class="display" style="font-size:1.45rem">Academia.</span>
          <span class="mono muted">LMS / 26</span>
        </a>
        <nav class="nav-links mono">
          <a href="#/courses">Catalog</a>
          ${user ? `<a href="#/dashboard">Dashboard</a>` : ""}
          ${user && ["admin", "instructor"].includes(user.role) ? `<a href="#/instructor">Instructor</a>` : ""}
          ${user && user.role === "admin" ? `<a href="#/admin">Admin</a>` : ""}
        </nav>
        <div class="actions">
          ${
            user
              ? `<span class="badge dark">${esc(user.role)}</span><button class="btn ghost" onclick="LMS.logout()">Logout</button>`
              : `<a class="btn ghost" href="#/login">Sign In</a><a class="btn accent" href="#/register">Join</a>`
          }
        </div>
      </div>
    </header>
  `;
}

function footer() {
  return `<footer class="footer mono">Academia LMS - Employee learning, certificates, quizzes, assignments, and AI support.</footer>`;
}

function requireAuth(roleList) {
  if (!state.user) {
    return `<main class="container"><div class="notice"><p class="mono">Authentication required</p><h1 class="display section-title">Sign in to continue.</h1><a class="btn accent" href="#/login">Sign In</a></div></main>`;
  }
  if (roleList && !roleList.includes(state.user.role)) {
    return `<main class="container"><div class="notice"><p class="mono error">Forbidden</p><h1 class="display section-title">This desk is reserved.</h1><a class="btn" href="#/dashboard">Back to dashboard</a></div></main>`;
  }
  return "";
}

function courseCard(course) {
  return `
    <a href="#/course/${course.id}" class="card">
      <img class="course-image" src="${esc(course.cover_url)}" alt="${esc(course.title)}">
      <div style="padding:22px">
        <div class="row" style="margin-bottom:12px">
          <span class="badge dark">${esc(course.category)}</span>
          <span class="badge">${esc(course.level)}</span>
        </div>
        <h3 class="display" style="font-size:1.55rem;margin:0 0 10px">${esc(course.title)}</h3>
        <p class="muted" style="line-height:1.55">${esc(course.description)}</p>
        <div class="row mono muted" style="justify-content:space-between;margin-top:18px">
          <span>${course.total_lessons} lessons</span>
          <span>${esc(course.instructor_name)}</span>
        </div>
      </div>
    </a>
  `;
}

async function homePage() {
  const courses = await request("/courses");
  return `
    <main>
      <section class="hero">
        <div class="container hero-grid">
          <div>
            <span class="badge accent">Issue 01</span>
            <h1 class="display">Train your people like <em>you mean it.</em></h1>
            <p>Academia is an editorial-grade Employee LMS for teams that want sharp courses, measurable progress, certificates, quizzes, assignments, discussions, and role-based workflows.</p>
            <div class="row" style="margin-top:30px">
              <a class="btn accent" href="#/register">Start Learning</a>
              <a class="btn ghost" href="#/courses">Browse Catalog</a>
            </div>
          </div>
          <div class="card">
            <img src="https://images.unsplash.com/photo-1684403798139-289e0f7fa5da?w=1200" alt="Modern learning space" style="height:440px;width:100%;object-fit:cover;border-bottom:1px solid var(--ink)">
            <div style="padding:24px">
              <p class="mono muted">Editor's Pick</p>
              <h2 class="display" style="margin:0;font-size:2rem">The architecture of better teams.</h2>
            </div>
          </div>
        </div>
      </section>
      <section class="container">
        <p class="mono muted">Featured</p>
        <h2 class="display section-title">This week's reading list.</h2>
        <div class="grid grid-3">${courses.slice(0, 3).map(courseCard).join("")}</div>
      </section>
    </main>
  `;
}

function loginPage() {
  return `
    <main class="container">
      <div class="grid grid-2">
        <section class="card pad" style="background:var(--ink);color:#fff">
          <p class="mono muted" style="color:#bbb">Academia / Login</p>
          <h1 class="display section-title">Welcome back to your reading list.</h1>
          <p style="color:#ddd;line-height:1.7">Use one of the demo accounts or sign in with your own seeded user.</p>
        </section>
        <form class="card pad" onsubmit="LMS.login(event)">
          <p class="mono muted">Sign In</p>
          <h2 class="display" style="font-size:2.4rem;margin-top:0">Enter the building.</h2>
          <label class="label mono">Email</label>
          <input class="input" id="login-email" type="email" required>
          <label class="label mono" style="margin-top:18px">Password</label>
          <input class="input" id="login-password" type="password" required>
          <p id="login-error" class="mono error"></p>
          <button class="btn accent" type="submit">Sign In</button>
          <div class="row" style="margin-top:24px">
            <button type="button" class="btn ghost" onclick="LMS.fillLogin('admin@lms.com','Admin@123')">Admin</button>
            <button type="button" class="btn ghost" onclick="LMS.fillLogin('instructor@lms.com','Instructor@123')">Instructor</button>
            <button type="button" class="btn ghost" onclick="LMS.fillLogin('employee@lms.com','Employee@123')">Employee</button>
          </div>
        </form>
      </div>
    </main>
  `;
}

function registerPage() {
  return `
    <main class="container">
      <form class="card pad" style="max-width:680px;margin:0 auto" onsubmit="LMS.register(event)">
        <p class="mono muted">Register</p>
        <h1 class="display section-title">Open a new chapter.</h1>
        <label class="label mono">Full name</label>
        <input class="input" id="reg-name" required>
        <label class="label mono" style="margin-top:18px">Email</label>
        <input class="input" id="reg-email" type="email" required>
        <label class="label mono" style="margin-top:18px">Password</label>
        <input class="input" id="reg-password" type="password" minlength="6" required>
        <label class="label mono" style="margin-top:18px">Role</label>
        <select class="select" id="reg-role"><option value="employee">Employee</option><option value="instructor">Instructor</option></select>
        <p id="reg-error" class="mono error"></p>
        <button class="btn accent" type="submit">Create Account</button>
      </form>
    </main>
  `;
}

async function catalogPage() {
  const params = new URLSearchParams();
  Object.entries(state.filters).forEach(([k, v]) => v && params.set(k, v));
  const [courses, categories] = await Promise.all([request("/courses?" + params), request("/courses/categories")]);
  return `
    <main>
      <section class="container" style="border-bottom:1px solid var(--ink)">
        <p class="mono muted">The Catalog</p>
        <h1 class="display section-title">Every course worth finishing.</h1>
        <div class="grid grid-4 card pad">
          <input class="input" placeholder="Search courses" value="${esc(state.filters.q)}" oninput="LMS.setFilter('q', this.value)">
          <select class="select" onchange="LMS.setFilter('category', this.value)">
            ${["All", ...categories].map((c) => `<option ${state.filters.category === c ? "selected" : ""}>${esc(c)}</option>`).join("")}
          </select>
          <select class="select" onchange="LMS.setFilter('level', this.value)">
            ${["All", "Beginner", "Intermediate", "Advanced"].map((l) => `<option ${state.filters.level === l ? "selected" : ""}>${l}</option>`).join("")}
          </select>
          <button class="btn ghost" onclick="LMS.clearFilters()">Clear</button>
        </div>
      </section>
      <section class="container">
        ${courses.length ? `<div class="grid grid-3">${courses.map(courseCard).join("")}</div>` : `<div class="notice mono">No courses match this filter.</div>`}
      </section>
    </main>
  `;
}

async function courseDetailPage(id) {
  const course = await request(`/courses/${id}`);
  const quizzes = await request(`/quizzes/course/${id}`);
  let enrollment = null;
  if (state.user) {
    const rows = await request("/enrollments");
    enrollment = rows.find((e) => e.course_id === id);
  }
  const firstLesson = course.modules[0]?.lessons[0]?.id;
  return `
    <main>
      <section class="container grid grid-2" style="border-bottom:1px solid var(--ink)">
        <div>
          <p class="mono muted">Course / ${esc(course.category)}</p>
          <h1 class="display section-title">${esc(course.title)}</h1>
          <p class="muted" style="font-size:1.1rem;line-height:1.7">${esc(course.description)}</p>
          <div class="row" style="margin:22px 0">
            <span class="badge dark">${esc(course.category)}</span>
            <span class="badge">${esc(course.level)}</span>
            <span class="badge">${course.total_lessons} lessons</span>
          </div>
          ${
            enrollment
              ? `<a class="btn accent" href="#/learn/${course.id}/${firstLesson}">Continue Learning</a>`
              : `<button class="btn accent" onclick="LMS.enroll('${course.id}')">Enroll For Free</button>`
          }
        </div>
        <div class="card"><img src="${esc(course.cover_url)}" alt="${esc(course.title)}" style="height:390px;width:100%;object-fit:cover"></div>
      </section>
      <section class="container">
        <p class="mono muted">Syllabus</p>
        <h2 class="display" style="font-size:2.6rem">The full reading order.</h2>
        <div class="grid">
          ${course.modules
            .map(
              (m, i) => `
              <div class="card pad">
                <p class="mono muted">Module ${i + 1}</p>
                <h3 class="display" style="font-size:1.7rem;margin:0 0 12px">${esc(m.title)}</h3>
                ${m.lessons
                  .map(
                    (l, j) => `
                    <div class="row" style="justify-content:space-between;border-top:1px solid #ddd;padding:12px 0">
                      <span>${j + 1}. ${esc(l.title)} <span class="badge">${esc(l.content_type)}</span></span>
                      <span class="mono muted">${l.duration_min}m</span>
                    </div>`
                  )
                  .join("")}
              </div>`
            )
            .join("")}
        </div>
        ${
          quizzes.length
            ? `<h2 class="display" style="font-size:2.2rem;margin-top:40px">Assessments</h2><div class="grid grid-2">${quizzes
                .map((q) => `<a class="card pad" href="#/quiz/${q.id}"><span class="badge dark">Quiz</span><h3 class="display">${esc(q.title)}</h3><p class="mono muted">${q.questions.length} questions / ${q.passing_score}% to pass</p></a>`)
                .join("")}</div>`
            : ""
        }
      </section>
    </main>
  `;
}

async function lessonPage(courseId, lessonId) {
  const gate = requireAuth();
  if (gate) return gate;
  const [course, enrollments] = await Promise.all([request(`/courses/${courseId}`), request("/enrollments")]);
  const enrollment = enrollments.find((e) => e.course_id === courseId);
  const allLessons = course.modules.flatMap((m) => m.lessons.map((l) => ({ ...l, module: m.title })));
  const lesson = allLessons.find((l) => l.id === lessonId) || allLessons[0];
  const comments = await request(`/comments/lesson/${lesson.id}`);
  return `
    <main class="split">
      <aside class="sidebar">
        <div class="pad" style="padding:18px;border-bottom:1px solid var(--ink)">
          <a class="mono" href="#/course/${course.id}">Back to course</a>
          <h2 class="display" style="font-size:1.4rem">${esc(course.title)}</h2>
          <div class="progress"><span style="width:${enrollment?.progress || 0}%"></span></div>
          <p class="mono muted">${enrollment?.progress || 0}% complete</p>
        </div>
        ${course.modules
          .map(
            (m) => `
          <div>
            <p class="mono muted" style="padding:14px 18px;margin:0">${esc(m.title)}</p>
            ${m.lessons
              .map((l) => {
                const done = enrollment?.completed_lessons?.includes(l.id);
                return `<a class="lesson-link ${l.id === lesson.id ? "active" : ""}" href="#/learn/${course.id}/${l.id}">${done ? "[x]" : "[ ]"} ${esc(l.title)}</a>`;
              })
              .join("")}
          </div>`
          )
          .join("")}
      </aside>
      <section>
        <div class="container">
          <p class="mono muted">Lesson / ${esc(lesson.content_type)}</p>
          <h1 class="display section-title">${esc(lesson.title)}</h1>
          ${
            lesson.content_type === "video" && lesson.video_url
              ? `<iframe title="${esc(lesson.title)}" src="${esc(lesson.video_url)}" style="width:100%;aspect-ratio:16/9;border:1px solid var(--ink)"></iframe>`
              : `<article class="card pad" style="font-size:1.1rem;line-height:1.8">${esc(lesson.body)}</article>`
          }
          <div class="row" style="margin-top:24px">
            <button class="btn accent" onclick="LMS.completeLesson('${course.id}','${lesson.id}')">Mark Complete</button>
            <a class="btn ghost" href="#/course/${course.id}">Course Detail</a>
          </div>
        </div>
        <div class="container" style="border-top:1px solid var(--ink)">
          <p class="mono muted">Discussion / ${comments.length}</p>
          <form class="row" onsubmit="LMS.comment(event,'${course.id}','${lesson.id}')">
            <input class="input" id="comment-text" placeholder="Share a thought">
            <button class="btn">Post</button>
          </form>
          <div class="grid" style="margin-top:20px">
            ${comments.map((c) => `<div class="card pad"><p class="mono muted">${esc(c.user_name)} / ${esc(c.user_role)}</p><p>${esc(c.text)}</p></div>`).join("")}
          </div>
        </div>
      </section>
    </main>
  `;
}

async function dashboardPage() {
  const gate = requireAuth();
  if (gate) return gate;
  const [enrollments, recs, certs] = await Promise.all([request("/enrollments"), request("/ai/recommendations"), request("/certificates")]);
  return `
    <main>
      <section class="container" style="border-bottom:1px solid var(--ink)">
        <p class="mono muted">Dashboard</p>
        <h1 class="display section-title">Good to see you, <em>${esc(state.user.name.split(" ")[0])}</em>.</h1>
        <div class="grid grid-3">
          <div class="card pad"><p class="mono muted">Enrolled</p><h2 class="display">${enrollments.length}</h2></div>
          <div class="card pad"><p class="mono muted">Completed</p><h2 class="display">${enrollments.filter((e) => e.completed).length}</h2></div>
          <div class="card pad"><p class="mono muted">Certificates</p><h2 class="display">${certs.length}</h2></div>
        </div>
      </section>
      <section class="container">
        <p class="mono muted">Continue</p>
        <h2 class="display" style="font-size:2.5rem">In progress</h2>
        ${
          enrollments.length
            ? `<div class="grid grid-3">${enrollments
                .map(
                  (e) => `
                <a class="card" href="#/course/${e.course_id}">
                  <img class="course-image" src="${esc(e.course?.cover_url || "")}" alt="">
                  <div style="padding:22px">
                    <h3 class="display">${esc(e.course?.title || "Course")}</h3>
                    <div class="progress"><span style="width:${e.progress}%"></span></div>
                    <p class="mono muted">${e.progress}% complete</p>
                  </div>
                </a>`
                )
                .join("")}</div>`
            : `<div class="notice">No active courses yet. <a class="mono" href="#/courses">Browse catalog</a></div>`
        }
      </section>
      <section class="container" style="background:var(--ink);color:#fff;max-width:none">
        <div style="max-width:1400px;margin:0 auto">
          <p class="mono" style="color:#bbb">AI Recommendations / ${esc(recs.model || "")}</p>
          <h2 class="display" style="font-size:3rem">Picked for you.</h2>
          <p style="color:#ddd">${esc(recs.reason)}</p>
          <div class="grid grid-3">${recs.recommendations.map(courseCard).join("")}</div>
        </div>
      </section>
      <section class="container">
        <p class="mono muted">Certificates</p>
        <div class="grid grid-3">${certs.map((c) => `<a class="card pad" href="#/certificate/${c.id}"><span class="badge dark">Certificate</span><h3 class="display">${esc(c.course_title)}</h3><p class="mono muted">${new Date(c.issued_at).toLocaleDateString()}</p></a>`).join("") || `<div class="notice">Finish a course to earn a certificate.</div>`}</div>
      </section>
    </main>
  `;
}

async function quizPage(id) {
  const gate = requireAuth();
  if (gate) return gate;
  if (!state.quizCache[id]) state.quizCache[id] = await request(`/quizzes/${id}`);
  const quiz = state.quizCache[id];
  const answers = state.quizAnswers[id] || Array(quiz.questions.length).fill(-1);
  state.quizAnswers[id] = answers;
  return `
    <main class="container" style="max-width:920px">
      <p class="mono muted">Assessment</p>
      <h1 class="display section-title">${esc(quiz.title)}</h1>
      ${quiz.questions
        .map(
          (q, i) => `
        <section class="card pad" style="margin-bottom:22px">
          <p class="mono muted">Question ${i + 1} / ${quiz.questions.length}</p>
          <h2 class="display" style="font-size:1.7rem">${esc(q.question)}</h2>
          <div class="grid">
            ${q.options
              .map((opt, oi) => `<button class="btn ${answers[i] === oi ? "accent" : "ghost"}" onclick="LMS.answer('${id}',${i},${oi})">${String.fromCharCode(65 + oi)}. ${esc(opt)}</button>`)
              .join("")}
          </div>
        </section>`
        )
        .join("")}
      <button class="btn accent" ${answers.includes(-1) ? "disabled" : ""} onclick="LMS.submitQuiz('${id}')">Submit Quiz</button>
      <div id="quiz-result"></div>
    </main>
  `;
}

async function certificatePage(id) {
  const cert = await request(`/certificates/${id}`);
  return `
    <main class="container">
      <section class="card pad" style="max-width:880px;margin:0 auto;text-align:center;padding:56px">
        <p class="mono muted">Certificate of Completion</p>
        <h1 class="display section-title">This certifies that</h1>
        <h2 class="display" style="font-size:3rem;color:var(--accent)">${esc(cert.user_name)}</h2>
        <p class="mono muted">has successfully completed</p>
        <h3 class="display" style="font-size:2.2rem">${esc(cert.course_title)}</h3>
        <div class="row mono muted" style="justify-content:space-between;margin-top:48px;border-top:1px solid var(--ink);padding-top:20px">
          <span>Issued ${new Date(cert.issued_at).toLocaleDateString()}</span>
          <span>No. ${esc(cert.id.slice(0, 8).toUpperCase())}</span>
        </div>
      </section>
    </main>
  `;
}

async function instructorPage() {
  const gate = requireAuth(["admin", "instructor"]);
  if (gate) return gate;
  const courses = await request("/courses");
  return `
    <main class="container">
      <p class="mono muted">Instructor Studio</p>
      <h1 class="display section-title">Build the next chapter.</h1>
      <div class="grid grid-2">
        <form class="card pad" onsubmit="LMS.createCourse(event)">
          <h2 class="display">Create course</h2>
          <input class="input" id="course-title" placeholder="Course title" required>
          <textarea class="textarea" id="course-desc" placeholder="Description" required></textarea>
          <div class="grid grid-2">
            <input class="input" id="course-cat" placeholder="Category" value="Leadership">
            <select class="select" id="course-level"><option>Beginner</option><option>Intermediate</option><option>Advanced</option></select>
          </div>
          <input class="input" id="course-cover" placeholder="Cover image URL" value="https://images.unsplash.com/photo-1556761175-b413da4baf72?w=1200">
          <input class="input" id="module-title" placeholder="Module title" value="Module 1">
          <input class="input" id="lesson-title" placeholder="Lesson title" value="Opening lesson">
          <textarea class="textarea" id="lesson-body" placeholder="Lesson body">Write the core lesson material here.</textarea>
          <button class="btn accent" type="submit">Publish Course</button>
          <p id="course-msg" class="mono"></p>
        </form>
        <form class="card pad" onsubmit="LMS.generateQuiz(event)">
          <h2 class="display">AI quiz generator</h2>
          <select class="select" id="quiz-course" required>${courses.map((c) => `<option value="${c.id}">${esc(c.title)}</option>`).join("")}</select>
          <input class="input" id="quiz-topic" placeholder="Topic" required>
          <input class="input" id="quiz-count" type="number" min="1" max="10" value="5">
          <input class="input" id="quiz-title" placeholder="Quiz title" required>
          <button class="btn accent" type="submit">Generate Questions</button>
          <p id="quiz-msg" class="mono"></p>
          <div id="generated-quiz"></div>
        </form>
      </div>
    </main>
  `;
}

async function adminPage() {
  const gate = requireAuth(["admin"]);
  if (gate) return gate;
  const [stats, users] = await Promise.all([request("/admin/stats"), request("/users")]);
  return `
    <main class="container">
      <p class="mono muted">Control Room</p>
      <h1 class="display section-title">Admin desk.</h1>
      <div class="grid grid-4">
        ${["users", "courses", "enrollments", "certificates"].map((k) => `<div class="card pad"><p class="mono muted">${k}</p><h2 class="display">${stats[k]}</h2></div>`).join("")}
      </div>
      <h2 class="display" style="font-size:2.4rem;margin-top:42px">Users</h2>
      <table class="table">
        <thead><tr><th>Name</th><th>Email</th><th>Role</th><th>Change</th></tr></thead>
        <tbody>${users
          .map(
            (u) => `
          <tr>
            <td>${esc(u.name)}</td>
            <td class="mono">${esc(u.email)}</td>
            <td><span class="badge dark">${esc(u.role)}</span></td>
            <td><select onchange="LMS.changeRole('${u.id}',this.value)"><option ${u.role === "employee" ? "selected" : ""}>employee</option><option ${u.role === "instructor" ? "selected" : ""}>instructor</option><option ${u.role === "admin" ? "selected" : ""}>admin</option></select></td>
          </tr>`
          )
          .join("")}</tbody>
      </table>
    </main>
  `;
}

async function render() {
  if (!state.ready) await loadMe();
  const path = route();
  const parts = path.split("/").filter(Boolean);
  let body;
  try {
    if (path === "/") body = await homePage();
    else if (path === "/login") body = loginPage();
    else if (path === "/register") body = registerPage();
    else if (path === "/courses") body = await catalogPage();
    else if (parts[0] === "course") body = await courseDetailPage(parts[1]);
    else if (parts[0] === "learn") body = await lessonPage(parts[1], parts[2]);
    else if (path === "/dashboard") body = await dashboardPage();
    else if (parts[0] === "quiz") body = await quizPage(parts[1]);
    else if (parts[0] === "certificate") body = await certificatePage(parts[1]);
    else if (path === "/instructor") body = await instructorPage();
    else if (path === "/admin") body = await adminPage();
    else body = `<main class="container"><h1 class="display section-title">Page not found.</h1></main>`;
  } catch (error) {
    body = `<main class="container"><div class="notice"><p class="mono error">Error</p><h1 class="display">${esc(error.message)}</h1><button class="btn" onclick="LMS.refresh()">Retry</button></div></main>`;
  }
  app.innerHTML = nav() + body + footer();
}

window.LMS = {
  refresh: render,
  fillLogin(email, password) {
    document.getElementById("login-email").value = email;
    document.getElementById("login-password").value = password;
  },
  async login(event) {
    event.preventDefault();
    try {
      state.user = await request("/auth/login", {
        method: "POST",
        body: JSON.stringify({
          email: document.getElementById("login-email").value,
          password: document.getElementById("login-password").value,
        }),
      });
      go("/dashboard");
    } catch (error) {
      document.getElementById("login-error").textContent = error.message;
    }
  },
  async register(event) {
    event.preventDefault();
    try {
      state.user = await request("/auth/register", {
        method: "POST",
        body: JSON.stringify({
          name: document.getElementById("reg-name").value,
          email: document.getElementById("reg-email").value,
          password: document.getElementById("reg-password").value,
          role: document.getElementById("reg-role").value,
        }),
      });
      go("/dashboard");
    } catch (error) {
      document.getElementById("reg-error").textContent = error.message;
    }
  },
  async logout() {
    await request("/auth/logout", { method: "POST" });
    state.user = null;
    go("/");
    render();
  },
  setFilter(key, value) {
    state.filters[key] = value;
    clearTimeout(window.__filterTimer);
    window.__filterTimer = setTimeout(render, 180);
  },
  clearFilters() {
    state.filters = { category: "All", level: "All", q: "" };
    render();
  },
  async enroll(courseId) {
    if (!state.user) return go("/login");
    const enrollment = await request(`/enrollments/${courseId}`, { method: "POST" });
    const course = await request(`/courses/${courseId}`);
    const first = course.modules[0]?.lessons[0]?.id;
    go(first ? `/learn/${courseId}/${first}` : `/course/${courseId}`);
    return enrollment;
  },
  async completeLesson(courseId, lessonId) {
    const updated = await request(`/enrollments/${courseId}/lesson/${lessonId}/complete`, { method: "POST" });
    if (updated.completed) go("/dashboard");
    else render();
  },
  async comment(event, courseId, lessonId) {
    event.preventDefault();
    const input = document.getElementById("comment-text");
    if (!input.value.trim()) return;
    await request("/comments", {
      method: "POST",
      body: JSON.stringify({ course_id: courseId, lesson_id: lessonId, text: input.value }),
    });
    render();
  },
  answer(quizId, questionIndex, optionIndex) {
    state.quizAnswers[quizId][questionIndex] = optionIndex;
    render();
  },
  async submitQuiz(quizId) {
    const result = await request(`/quizzes/${quizId}/submit`, {
      method: "POST",
      body: JSON.stringify({ answers: state.quizAnswers[quizId] }),
    });
    document.getElementById("quiz-result").innerHTML = `
      <div class="notice" style="margin-top:24px">
        <p class="mono ${result.passed ? "success-text" : "error"}">${result.passed ? "Passed" : "Try again"}</p>
        <h2 class="display" style="font-size:3rem">${result.score}%</h2>
        <div class="grid">${result.detail.map((d) => `<div class="card pad"><strong>${esc(d.question)}</strong><p class="mono muted">Your answer: ${d.user_answer + 1 || "-"} / Correct: ${d.correct_index + 1}</p><p>${esc(d.explanation)}</p></div>`).join("")}</div>
      </div>`;
  },
  async createCourse(event) {
    event.preventDefault();
    const body = {
      title: document.getElementById("course-title").value,
      description: document.getElementById("course-desc").value,
      category: document.getElementById("course-cat").value,
      level: document.getElementById("course-level").value,
      cover_url: document.getElementById("course-cover").value,
      modules: [
        {
          title: document.getElementById("module-title").value,
          lessons: [
            {
              title: document.getElementById("lesson-title").value,
              content_type: "text",
              body: document.getElementById("lesson-body").value,
              duration_min: 8,
            },
          ],
        },
      ],
    };
    const course = await request("/courses", { method: "POST", body: JSON.stringify(body) });
    document.getElementById("course-msg").textContent = `Created: ${course.title}`;
  },
  async generateQuiz(event) {
    event.preventDefault();
    const courseId = document.getElementById("quiz-course").value;
    const title = document.getElementById("quiz-title").value;
    const msg = document.getElementById("quiz-msg");
    msg.textContent = "Generating...";
    const generated = await request("/ai/generate-quiz", {
      method: "POST",
      body: JSON.stringify({
        course_id: courseId,
        topic: document.getElementById("quiz-topic").value,
        num_questions: Number(document.getElementById("quiz-count").value || 5),
      }),
    });
    state.generatedQuiz = { courseId, title, questions: generated.questions };
    msg.textContent = `Generated with ${generated.model}.`;
    document.getElementById("generated-quiz").innerHTML = `
      <div class="notice">
        <p class="mono">Preview</p>
        ${generated.questions.map((q, i) => `<div class="card pad" style="margin-top:12px"><strong>Q${i + 1}. ${esc(q.question)}</strong><ol>${q.options.map((o) => `<li>${esc(o)}</li>`).join("")}</ol></div>`).join("")}
        <button class="btn accent" onclick="LMS.saveGeneratedQuiz()">Save Quiz</button>
      </div>`;
  },
  async saveGeneratedQuiz() {
    const draft = state.generatedQuiz;
    if (!draft) return;
    await request("/quizzes", {
      method: "POST",
      body: JSON.stringify({ course_id: draft.courseId, title: draft.title, passing_score: 70, questions: draft.questions }),
    });
    document.getElementById("quiz-msg").textContent = "Quiz saved.";
  },
  async changeRole(userId, role) {
    await request(`/users/${userId}/role`, { method: "PATCH", body: JSON.stringify({ role }) });
    render();
  },
};

window.addEventListener("hashchange", render);
render();
