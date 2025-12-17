// app.js
console.log("Starting process...");

// Force a failure for testing
const isCriticalConditionMet = false; 

if (!isCriticalConditionMet) {
  console.error("Error: Critical failure detected!");
  process.exit(1); // <--- This '1' tells GitHub the job FAILED
}
