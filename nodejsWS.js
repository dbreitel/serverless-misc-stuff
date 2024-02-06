export const handler = async (event) => {
  // TODO implement
  const currentDate = new Date().toISOString().split('T')[0]; // Get current date in YYYY-MM-DD format
  const randomNum = Math.floor(Math.random() * 28) + 1; // Generate random number between 1 and 28
  const response = {
    statusCode: 200,
    body: JSON.stringify({ currentDate, randomNum }),
  
  };
  return response;
};
