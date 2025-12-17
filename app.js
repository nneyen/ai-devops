//app.js
// script is designe to automatically fail in CI/CD pipeline
console.log("Starting critical process...");
if (true) {
    // Intentional error: missing closing bracket or undefined variable
    console.log(undefinedVariable);
