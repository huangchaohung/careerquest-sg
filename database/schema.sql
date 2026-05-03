CREATE TABLE occupations (
    occupation_id SERIAL PRIMARY KEY,
    name VARCHAR(100) UNIQUE NOT NULL,
    sector VARCHAR(100),
    description TEXT,
    salary_min INT,
    salary_median INT,
    salary_max INT,
    demand_score FLOAT
);

CREATE TABLE skills (
    skill_id SERIAL PRIMARY KEY,
    name VARCHAR(100) UNIQUE NOT NULL,
    category VARCHAR(100)
);

CREATE TABLE courses (
    course_id SERIAL PRIMARY KEY,
    title VARCHAR(255) NOT NULL,
    provider VARCHAR(255),
    skill_id INT REFERENCES skills(skill_id),
    cost FLOAT,
    duration_hours FLOAT,
    difficulty VARCHAR(50),
    source_url TEXT
);

CREATE TABLE occupation_skills (
    occupation_id INT REFERENCES occupations(occupation_id),
    skill_id INT REFERENCES skills(skill_id),
    importance INT,
    PRIMARY KEY (occupation_id, skill_id)
);

CREATE TABLE career_transitions (
    transition_id SERIAL PRIMARY KEY,
    from_occupation_id INT REFERENCES occupations(occupation_id),
    to_occupation_id INT REFERENCES occupations(occupation_id),
    transition_type VARCHAR(50),
    estimated_months INT,
    estimated_cost FLOAT,
    difficulty INT,
    notes TEXT
);