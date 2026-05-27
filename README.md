# dl-candidate

## Assignment: Legal Document Data Extraction

This task is designed to assess your problem-solving skills, code quality, and ability to work with an end-to-end process.

## The Challenge

The core challenge of this assignment is to build a solution that can extract structured data from a provided legal document using a **VLM**.

You will be given a sample legal document in PDF. Your task is to use a method of your choice to:

1. **Process the Document**: Handle the input PDF or image, preparing it for text recognition.

2. **Identify Key Information**: Extract specific information from each page. For example, you might need to extract a case number, party names, or specific clauses.

3. **Present Results**: Store the extracted data in a structured format (e.g., a JSON object) and showcase the entire process in a simple Streamlit web application.

We're not looking for a perfect, production-ready system. We want to see how you approach the problem, what tools and libraries you choose to use, and how you structure your code.

## Specific Data Points to Extract

The basic characteristics of a property deed (Τα βασικά χαρακτηριστικά ενός τίτλου ιδιοκτησίας) include:

### Involved Parties (Ενεχόμενοι-συμβαλλόμενα μέρη)

- **Names and details** (Tax ID numbers, addresses, identity documents) of the seller and buyer, and/or their representatives (as there may be a legal representative attorney who will sign it).

- **Note**: There may be more than one seller or buyer. When there are multiple buyers or sellers, we have a list. The same applies to their representatives.

- In the case of parental provision, the seller is considered to be the parent(s) and the buyer is the child(ren).

- The number of contracting parties is always shown in their signatures on the last page.

- **Notary details**.

### Property Details (Στοιχεία ακινήτου)

- **Location** (Address, municipal unit, area, building block).

- **Type of property** (apartment, store, plot, etc.).

- **Area, floor** (e.g., E2).

- **Land registry details** - KAEK (Κτηματολογικά στοιχεία - ΚΑΕΚ).

- **Building permit number** (where applicable).

## Getting Started

You can start by cloning this repository. The sample legal document (`simbolaio-agorapolisias-public.pdf`) is included in the repository.

## Deliverables

Your submission should include:

1. **Your Code**: The complete source code for your solution, including the Streamlit application.

2. **A Brief Write-up**: A short document (either in the README itself or a separate file) that explains:
   - Your overall approach and design decisions.
   - The tools, frameworks, and libraries you used and why.
   - Any assumptions you made.

3. **Instructions**: Clear, simple instructions on how to set up and run your code, including how to launch the Streamlit app.

**Note**: While not mandatory, it is recommended to containerize your Streamlit application using Docker for easier deployment and reproducibility.

## Evaluation & Comparison (Optional but Strongly Recommended)

Once you have a working pipeline, reflect on its quality. How do you know it performs well? Consider running your extraction across more than one configuration — this could mean different models, different prompt strategies, or different pre-processing approaches.

Design your own evaluation methodology: decide what to measure, how to measure it, and how to present your findings in a structured, comparable way.  Focus your comparison on the quality of extraction (**accuracy**) and runtime performance (**speed**)

## Optional Enhancements

If you have extra time and want to showcase your skills further, consider implementing one or more of the following:

- **Error Handling**: Implement robust error handling for cases where text or data cannot be reliably extracted.

- **Multiple Document Types**: Design your solution to handle different legal document formats, even if you only process one as a primary example.

- **Performance Optimization**: Comment on potential bottlenecks and how you would optimize your solution for speed or scale.
