"""
Built-in sample postings, used when USE_MOCK_JOBS is set or when no RapidAPI
key is configured.

This exists so the whole pipeline can be developed and demonstrated without
spending job-search API quota - each live search costs one call per selected
title. The shape here is deliberately identical to what job_search.py returns
for a real posting, including `salary` as a {min, max} object. It previously
used a bare number, which meant any code that rendered salary broke the moment
live results were switched on.
"""

MOCK_JOBS = [
    {
        "id": "mock-1",
        "title": "Frontend Developer",
        "company": "Meta",
        "location": "Bangalore, Karnataka, IN",
        "type": "FULLTIME",
        "description": (
            "We are looking for a Frontend Developer to build scalable, responsive, and "
            "user-friendly web applications. The ideal candidate should have strong experience "
            "with React, JavaScript, TypeScript, HTML, CSS, and modern frontend development "
            "practices. Responsibilities include developing reusable UI components, integrating "
            "REST APIs, optimizing application performance, and collaborating with product "
            "managers and designers. Experience with Git, responsive design, accessibility, and "
            "Agile development is preferred. Knowledge of testing frameworks such as Jest is a plus."
        ),
        "apply_link": "https://example.com/jobs/mock-1",
        "is_remote": False,
        "posted_at": "2026-09-01T09:30:00Z",
        "salary": {"min": 1200000, "max": 1800000},
    },
    {
        "id": "mock-2",
        "title": "Software Engineer",
        "company": "Anthropic",
        "location": "Hyderabad, Telangana, IN",
        "type": "FULLTIME",
        "description": (
            "We are seeking a Software Engineer to design, develop, test, and maintain scalable "
            "backend services. Candidates should have experience with Python, REST APIs, SQL, "
            "data structures, algorithms, and object-oriented programming. Responsibilities "
            "include building reliable backend services, designing and integrating RESTful APIs, "
            "working with relational databases, writing unit and integration tests, and improving "
            "system performance. Experience with cloud platforms, Git, Docker, CI/CD pipelines, "
            "and microservices architecture is preferred."
        ),
        "apply_link": "https://example.com/jobs/mock-2",
        "is_remote": True,
        "posted_at": "2026-09-03T14:15:00Z",
        "salary": {"min": 1600000, "max": 2200000},
    },
    {
        "id": "mock-3",
        "title": "Java Developer",
        "company": "Oracle",
        "location": "Chennai, Tamil Nadu, IN",
        "type": "FULLTIME",
        "description": (
            "We are looking for a Java Developer to design, develop, and maintain high-performance "
            "applications and distributed services. The candidate should have strong knowledge of "
            "Java, Spring Boot, REST APIs, object-oriented programming, data structures, "
            "algorithms, and SQL. Responsibilities include developing scalable microservices, "
            "implementing business logic, writing unit tests, and performing code reviews. "
            "Experience with Hibernate, PostgreSQL, Docker, Git, and CI/CD is highly desirable."
        ),
        "apply_link": "https://example.com/jobs/mock-3",
        "is_remote": False,
        "posted_at": "2026-09-05T10:00:00Z",
        "salary": {"min": 1100000, "max": 1700000},
    },
    {
        "id": "mock-4",
        "title": "Data Analyst",
        "company": "Flipkart",
        "location": "Bangalore, Karnataka, IN",
        "type": "FULLTIME",
        "description": (
            "We are seeking a Data Analyst to analyze business and customer data and generate "
            "actionable insights. The ideal candidate should have strong skills in SQL, Python, "
            "Excel, Power BI, data visualization, and statistical analysis. Responsibilities "
            "include collecting and cleaning datasets, writing complex SQL queries, building "
            "interactive dashboards, identifying trends, and presenting insights to stakeholders. "
            "Experience with pandas, NumPy, A/B testing, and data modeling is preferred."
        ),
        "apply_link": "https://example.com/jobs/mock-4",
        "is_remote": True,
        "posted_at": "2026-09-06T08:45:00Z",
        "salary": {"min": 800000, "max": 1200000},
    },
    {
        "id": "mock-5",
        "title": "Python Developer",
        "company": "Zoho",
        "location": "Pune, Maharashtra, IN",
        "type": "FULLTIME",
        "description": (
            "We are looking for a Python Developer to develop scalable applications, automation "
            "solutions, and backend services. Candidates should have experience with Python, "
            "FastAPI or Flask, REST APIs, SQL, Git, and object-oriented programming. "
            "Responsibilities include developing backend applications, designing REST APIs, "
            "integrating databases, automating workflows, and writing unit tests. Experience with "
            "PostgreSQL, pandas, Docker, Linux, and CI/CD is preferred. Knowledge of asynchronous "
            "programming and authentication is a plus."
        ),
        "apply_link": "https://example.com/jobs/mock-5",
        "is_remote": False,
        "posted_at": "2026-09-07T16:20:00Z",
        "salary": {"min": 600000, "max": 900000},
    },
    {
        "id": "mock-6",
        "title": "Machine Learning Engineer",
        "company": "NVIDIA",
        "location": "Remote, IN",
        "type": "FULLTIME",
        "description": (
            "We are seeking a Machine Learning Engineer to develop, train, evaluate, and deploy "
            "machine learning models for production AI applications. The ideal candidate should "
            "have strong knowledge of Python, machine learning, deep learning, statistics, feature "
            "engineering, and model evaluation. Experience with PyTorch or TensorFlow, "
            "scikit-learn, pandas, NumPy, SQL, and NLP is preferred. Experience with Docker, "
            "Kubernetes, cloud platforms, MLOps, Git, and REST APIs is highly desirable."
        ),
        "apply_link": "https://example.com/jobs/mock-6",
        "is_remote": True,
        "posted_at": "2026-09-08T12:00:00Z",
        "salary": {"min": 1800000, "max": 2600000},
    },
    {
        "id": "mock-7",
        "title": "Junior Full Stack Developer",
        "company": "Freshworks",
        "location": "Chennai, Tamil Nadu, IN",
        "type": "FULLTIME",
        "description": (
            "We are hiring a Junior Full Stack Developer to work across our web platform. You will "
            "build features in React on the frontend and Node.js or Python on the backend, working "
            "with REST APIs, SQL databases, and Git. This role suits a recent graduate with strong "
            "project work. Familiarity with HTML, CSS, JavaScript, and version control is required. "
            "Exposure to Docker, testing, and cloud deployment is a bonus but not expected."
        ),
        "apply_link": "https://example.com/jobs/mock-7",
        "is_remote": False,
        "posted_at": "2026-09-09T11:10:00Z",
        "salary": {"min": 500000, "max": 800000},
    },
    {
        "id": "mock-8",
        "title": "Backend Engineer",
        "company": "Razorpay",
        "location": "Bangalore, Karnataka, IN",
        "type": "FULLTIME",
        "description": (
            "Join our payments platform team as a Backend Engineer. You will design and operate "
            "high-throughput services using Python or Go, PostgreSQL, Redis, and Kafka. Strong "
            "fundamentals in data structures, algorithms, and distributed systems are required. "
            "Responsibilities include API design, database schema design, performance tuning, and "
            "on-call ownership of the services you build. Experience with AWS, Docker, Kubernetes, "
            "and observability tooling is preferred."
        ),
        "apply_link": "https://example.com/jobs/mock-8",
        "is_remote": True,
        "posted_at": "2026-09-10T09:00:00Z",
        "salary": {"min": 1500000, "max": 2400000},
    },
]
