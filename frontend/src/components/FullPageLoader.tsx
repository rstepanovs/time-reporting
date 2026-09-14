import { Center, Loader } from "@mantine/core";

export function FullPageLoader() {
  return (
    <Center mih="100vh">
      <Loader aria-label="Loading" />
    </Center>
  );
}
