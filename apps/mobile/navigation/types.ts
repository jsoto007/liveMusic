import type { NavigationProp } from "@react-navigation/native";

export type RootStackParamList = {
  Tabs: undefined;
  Show: { eventId: string };
  Band: { handle: string };
  Search: undefined;
  SignIn: undefined;
  Join: undefined;
};

export type TabParamList = {
  Bill: undefined;
  Plan: undefined;
  Post: undefined;
  List: undefined;
  You: undefined;
};

export type RootNavigation = NavigationProp<RootStackParamList>;
