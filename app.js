// app.js
console.log("Starting application...");

const dbUrl = process.env.DATABASE_URL;

// Intentional failure
if (!dbUrl) {
  throw new Error("DATABASE_URL is not set");
}

console.log("Connecting to database:", dbUrl);
console.log(undefinedVariable);
