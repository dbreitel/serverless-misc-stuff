export const handler = async (event) => {
  event.Records.forEach(record => {
    const { body } = record;
    console.log(body);
  });
  return {};
}
