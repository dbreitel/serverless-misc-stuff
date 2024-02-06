export const handler = async (event) => {
    try {
        // Access parameters from the URL
        const param1 = event.queryStringParameters.secret;
        const param2 = event.queryStringParameters.popass;
        const tokey = param1;
        const Signature = param2; 
        console.log(param1);
        console.log(Signature);
        // Create a response object
        const response = {
            statusCode: 200,
            body: JSON.stringify({
                queryParameters: event.queryStringParameters || {},
                tokey,
                Signature,
                message: 'Parameters received successfully!',
            }),
        };

        return response;
    } catch (error) {
        console.error('Error handling request:', error);

        // If there's an error, return an error response
        return {
            statusCode: 500,
            body: JSON.stringify({
                message: 'Error handling request',
                error: error.message,
            }),
        };
    }
};
